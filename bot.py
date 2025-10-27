"""
高性能 Telegram Bot - 用户查询功能
注重性能优化和异步处理
"""
import asyncio
import logging
import re
import json
import aiohttp
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.custom import InlineResults
import config
from database import Database

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # 生产环境使用INFO
)
logger = logging.getLogger(__name__)


class TelegramQueryBot:
    """Telegram 用户查询 Bot"""
    
    def __init__(self):
        """初始化 Bot"""
        # 创建客户端 - 使用性能优化参数
        self.client = TelegramClient(
            config.SESSION_NAME,
            config.API_ID,
            config.API_HASH,
            connection_retries=config.CONNECTION_RETRIES,
            request_retries=config.REQUEST_RETRIES,
            timeout=config.TIMEOUT,
            auto_reconnect=True,
            sequential_updates=False
        )
        
        # 信号量控制并发
        self.semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)
        
        # HTTP会话（复用连接）
        self.http_session = None
        
        # 数据库实例
        self.db = Database()
        
        # 缓存查询结果（用于分页）
        self.query_cache = {}
        
        # 缓存文本搜索结果（用于分页）
        self.text_search_cache = {}
        
        # 等待关键词搜索回复的消息ID集合
        self.pending_text_search = set()
        
        # 管理员模块（延迟初始化）
        self.admin_module = None
        
        # 邀请模块（延迟初始化）
        self.invite_module = None
        
        # 充值模块（延迟初始化）
        self.recharge_module = None
        
        # VIP模块（延迟初始化）
        self.vip_module = None
        
        # Bot用户名（启动后获取）
        self.bot_username = None
        
        # 注册事件处理器
        self._register_handlers()
    
    def _parse_username(self, text):
        """
        解析用户名，支持多种格式：
        - username
        - @username
        - t.me/username
        - https://t.me/username
        - 纯数字ID
        """
        text = text.strip()
        
        # 匹配 t.me 链接
        telegram_link = re.match(r'https?://t\.me/([a-zA-Z0-9_]+)', text)
        if telegram_link:
            return telegram_link.group(1)
        
        # 匹配 t.me/username (无协议)
        short_link = re.match(r't\.me/([a-zA-Z0-9_]+)', text)
        if short_link:
            return short_link.group(1)
        
        # 去除 @ 符号
        if text.startswith('@'):
            return text[1:]
        
        # 纯数字ID或用户名
        return text
    
    def _format_user_log(self, user):
        """
        格式化用户信息用于日志输出
        
        Args:
            user: Telethon User对象
        
        Returns:
            格式化的用户信息字符串
        """
        if not user:
            return "未知用户"
        
        # 用户ID
        user_id = user.id
        
        # 用户名
        username = f"@{user.username}" if user.username else "无用户名"
        
        # 姓名
        name_parts = []
        if hasattr(user, 'first_name') and user.first_name:
            name_parts.append(user.first_name)
        if hasattr(user, 'last_name') and user.last_name:
            name_parts.append(user.last_name)
        name = " ".join(name_parts) if name_parts else "无姓名"
        
        return f"{name} ({username}, ID:{user_id})"
    
    async def _query_api(self, user):
        """调用查询API"""
        if not self.http_session:
            self.http_session = aiohttp.ClientSession()
        
        url = f"{config.QUERY_API_URL}/api/query"
        headers = {'x-api-key': config.QUERY_API_KEY}
        params = {'user': user}
        
        logger.debug(f"请求URL: {url}")
        logger.debug(f"请求参数: user={user}")
        
        try:
            timeout = aiohttp.ClientTimeout(total=300)  # 5分钟超时
            async with self.http_session.get(url, headers=headers, params=params, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"API错误 {response.status}: {error_text}")
                    return None
        except asyncio.TimeoutError:
            logger.error("API请求超时")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"HTTP客户端错误: {e}")
            return None
        except Exception as e:
            logger.error(f"API请求异常: {type(e).__name__} - {e}")
            return None
    
    async def _search_text_api(self, text):
        """调用文本搜索API"""
        if not self.http_session:
            self.http_session = aiohttp.ClientSession()
        
        url = f"{config.QUERY_API_URL}/api/text"
        headers = {'x-api-key': config.QUERY_API_KEY}
        params = {'text': text}
        
        logger.debug(f"文本搜索URL: {url}")
        logger.debug(f"搜索关键词: {text}")
        
        try:
            timeout = aiohttp.ClientTimeout(total=300)  # 5分钟超时
            async with self.http_session.get(url, headers=headers, params=params, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"文本搜索API错误 {response.status}: {error_text}")
                    return None
        except asyncio.TimeoutError:
            logger.error("文本搜索API请求超时")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"文本搜索HTTP客户端错误: {e}")
            return None
        except Exception as e:
            logger.error(f"文本搜索API请求异常: {type(e).__name__} - {e}")
            return None
    
    def _format_text_search_results(self, data, page=1, search_cost=None, use_vip=False, vip_remaining=0):
        """
        格式化文本搜索结果
        page: 当前页码（从1开始）
        search_cost: 搜索费用（可选）
        use_vip: 是否使用VIP配额
        vip_remaining: VIP剩余次数
        """
        if not data or not data.get('success'):
            return None, None
        
        search_data = data.get('data', {})
        search_text = search_data.get('searchText', '')
        total = search_data.get('total', 0)
        results = search_data.get('results', [])
        
        if not results:
            return "❌ 未找到匹配的消息", None
        
        # 分页设置
        items_per_page = 10
        total_pages = (total + items_per_page - 1) // items_per_page if total > 0 else 1
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_results = results[start_idx:end_idx]
        
        # 构建消息
        result = f"🔍 <b>关键词搜索结果</b>\n\n"
        result += f"🔑 关键词: <code>{search_text}</code>\n"
        result += f"📊 共找到 <code>{total}</code> 条消息\n"
        result += f"📄 第 {page}/{total_pages} 页\n"
        
        # 添加扣费提醒（仅在第一页显示）
        if page == 1:
            if use_vip:
                result += f"💎 VIP免费查询 (今日剩余 {vip_remaining} 次)\n"
            elif search_cost is not None:
                cost_str = f'{int(search_cost)}' if search_cost == int(search_cost) else f'{search_cost:.2f}'
                result += f"💳 本次搜索消耗: <code>{cost_str}</code> 积分\n"
        
        result += "\n━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, msg in enumerate(page_results, start=start_idx + 1):
            # 用户信息
            username = msg.get('username', '')
            name = msg.get('name', '未知用户')
            # HTML转义用户名称
            name_escaped = name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;') if name else '未知用户'
            user_id = msg.get('user_id', '')
            
            # 群组信息
            group = msg.get('group', {})
            group_title = group.get('title', '未知群组')
            # HTML转义群组名称
            group_title_escaped = group_title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            group_username = group.get('username', '')
            is_private = group.get('isPrivate', False)
            
            # 消息链接
            message_link = msg.get('messageLink', '')
            
            # 构建用户名显示
            if username:
                user_display = f"@{username}"
            elif name:
                user_display = name_escaped
            else:
                user_display = "未知用户"
            
            # 如果有消息链接，整行作为链接
            if message_link:
                result += f"{i}. <a href='{message_link}'>{user_display} 在 {group_title_escaped}</a>\n"
            else:
                # 没有消息链接时，用户名可以链接到个人主页
                result += f"{i}. "
                if username:
                    user_link = f"https://t.me/{username}"
                    result += f"<a href='{user_link}'>{user_display}</a>"
                else:
                    result += user_display
                result += f" 在 {group_title_escaped}"
                if is_private:
                    result += f" 🔒"
                result += "\n"
        
        # 创建翻页按钮
        buttons = []
        row = []
        
        if page > 1:
            row.append(Button.inline('⬅️ 上一页', f'text_search_{search_text}_{page-1}'))
        else:
            row.append(Button.inline('🔒 上一页', f'noop'))
        
        row.append(Button.inline(f'{page}/{total_pages}', f'noop'))
        
        if page < total_pages:
            row.append(Button.inline('下一页 ➡️', f'text_search_{search_text}_{page+1}'))
        else:
            row.append(Button.inline('下一页 🔒', f'noop'))
        
        buttons.append(row)
        # 第三行：返回个人中心
        buttons.append([Button.inline('« 返回个人中心', 'cmd_balance')])
        
        return result, buttons
    
    def _format_user_info(self, data, view='groups', page=1, is_vip=False):
        """
        格式化用户信息
        view: 'groups', 'messages' 或 'related'
        page: 当前页码（从1开始）
        is_vip: 是否为VIP用户
        """
        if not data or not data.get('success'):
            return None, None
        
        user_data = data.get('data', {})
        basic_info = user_data.get('basicInfo', {})
        
        # 基础信息
        user_id = basic_info.get('id', user_data.get('userId', '未知'))
        username = basic_info.get('username', '')
        first_name = basic_info.get('first_name', '无')
        last_name = basic_info.get('last_name', '')
        is_active = basic_info.get('is_active', True)
        is_bot = basic_info.get('is_bot', False)
        
        # 统计信息
        message_count = user_data.get('messageCount', 0)
        groups_count = user_data.get('groupsCount', 0)
        common_groups_stat_count = user_data.get('commonGroupsStatCount', 0)
        
        # 构建基础信息部分
        result = "👤 用户信息\n\n"
        result += f"ID: <code>{user_id}</code>\n"
        if username:
            result += f"用户名: @{username}\n"
        else:
            result += f"用户名: 无\n"
        
        # 姓名历史
        names = user_data.get('names', [])
        
        # 确保names是列表且有内容
        if isinstance(names, list) and len(names) > 0:
            total_names = len(names)
            display_limit = 5
            remaining = total_names - display_limit if total_names > display_limit else 0
            
            # 显示姓名历史标题，包含总数和剩余未显示数
            if remaining > 0:
                result += f"\n📝 姓名历史 (共 {total_names} 条，还有 {remaining} 条未显示)\n"
            else:
                result += f"\n📝 姓名历史 (共 {total_names} 条)\n"
            
            # 限制只显示最近的5条姓名历史记录
            for name_record in names[:display_limit]:
                if isinstance(name_record, dict):
                    # 尝试多种可能的字段名
                    date = name_record.get('date_time') or name_record.get('date') or name_record.get('updated_at') or name_record.get('timestamp') or ''
                    name = (name_record.get('name') or 
                           name_record.get('first_name') or 
                           name_record.get('full_name') or '').strip()
                    
                    if name:
                        # 格式化日期
                        date_str = ''
                        if date:
                            try:
                                # 处理多种日期格式
                                if 'T' in str(date):
                                    dt = datetime.fromisoformat(str(date).replace('Z', '+00:00'))
                                    date_str = dt.strftime('%Y/%m/%d')
                                else:
                                    date_str = str(date)[:10] if len(str(date)) >= 10 else str(date)
                            except Exception as e:
                                logger.debug(f"Date parse error: {e}")
                                date_str = str(date)[:10] if len(str(date)) >= 10 else str(date)
                        
                        if date_str:
                            result += f"  • {date_str} → {name}\n"
                        else:
                            result += f"  • {name}\n"
        
        # 如果没有姓名历史，显示当前姓名
        if not (isinstance(names, list) and len(names) > 0):
            full_name = first_name
            if last_name:
                full_name += f" {last_name}"
            if full_name and full_name != '无':
                result += f"\n📝 姓名: {full_name}\n"
        
        # 状态和类型
        result += f"\n状态: {'✅ 活跃' if is_active else '⚠️ 非活跃'}\n"
        result += f"类型: {'🤖 Bot' if is_bot else '👤 用户'}\n"
        
        # 统计信息
        result += f"\n📊 统计信息\n"
        result += f"💬 发言数: {message_count}\n"
        result += f"👥 群组数: {groups_count}\n"
        if config.SHOW_RELATED_USERS and common_groups_stat_count > 0:
            result += f"🔗 关联用户: {common_groups_stat_count}\n"
        
        result += "\n━━━━━━━━━━━━━━━━━━\n"
        
        # 根据视图类型显示不同内容
        items_per_page = 10
        
        if view == 'groups':
            groups = user_data.get('groups', [])
            total_items = len(groups)
            total_pages = (total_items + items_per_page - 1) // items_per_page if total_items > 0 else 1
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_groups = groups[start_idx:end_idx]
            
            result += f"\n👥 群组列表 ({groups_count}) - 第 {page}/{total_pages} 页\n\n"
            
            if page_groups:
                for i, group in enumerate(page_groups, start=start_idx + 1):
                    chat = group.get('chat', {})
                    title = chat.get('title', '未知群组')
                    # HTML转义群组名称
                    title_escaped = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    chat_id = chat.get('id', '')
                    username_group = chat.get('username', '')
                    
                    # 构建群组链接
                    if username_group:
                        group_link = f"https://t.me/{username_group}"
                        result += f"  {i}. 👥 <a href='{group_link}'>{title_escaped}</a>\n"
                    else:
                        # 私有群组显示ID
                        result += f"  {i}. 👥 {title_escaped} (ID: <code>{chat_id}</code>)\n"
            else:
                result += "  暂无群组记录\n"
        
        elif view == 'messages':
            messages = user_data.get('messages', [])
            total_items = len(messages)
            total_pages = (total_items + items_per_page - 1) // items_per_page if total_items > 0 else 1
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_messages = messages[start_idx:end_idx]
            
            result += f"\n💬 发言记录 ({message_count}) - 第 {page}/{total_pages} 页\n\n"
            
            if page_messages:
                for i, msg in enumerate(page_messages, start=start_idx + 1):
                    # 获取消息文本
                    text = msg.get('text', '')
                    
                    # 检查媒体类型
                    media_code = msg.get('mediaCode')
                    media_name = msg.get('mediaName', '')
                    
                    if not text or text.strip() == '':
                        # 根据媒体代码显示类型
                        if media_name:
                            text = f'[{media_name}]'
                        elif media_code:
                            media_types = {
                                1: '[Photo]',
                                2: '[Video]',
                                3: '[Voice]',
                                4: '[Document]',
                                5: '[Sticker]',
                                8: '[GIF]',
                            }
                            text = media_types.get(media_code, '[媒体消息]')
                        else:
                            text = '[媒体消息]'
                    
                    # 限制文本长度，保留更多字符
                    display_text = text
                    if len(display_text) > 40:
                        display_text = display_text[:40] + '...'
                    
                    # HTML转义特殊字符
                    display_text_escaped = display_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    
                    # 使用API返回的link字段
                    link = msg.get('link', '')
                    
                    # 如果没有link字段，手动构建
                    if not link:
                        group = msg.get('group', {})
                        group_username = group.get('username', '')
                        group_id = group.get('id', '')
                        msg_id = msg.get('messageId', msg.get('id', ''))
                        
                        if group_username:
                            link = f"https://t.me/{group_username}/{msg_id}"
                        else:
                            # 处理私有群组链接
                            group_id_str = str(group_id)
                            if group_id_str.startswith('-100'):
                                group_id_str = group_id_str[4:]
                            link = f"https://t.me/c/{group_id_str}/{msg_id}"
                    
                    result += f"  {i}. 💬 <a href='{link}'>{display_text_escaped}</a>\n"
            else:
                result += "  暂无发言记录\n"
        
        elif view == 'related':
            common_groups_stat = user_data.get('commonGroupsStat', [])
            total_items = len(common_groups_stat)
            total_pages = (total_items + items_per_page - 1) // items_per_page if total_items > 0 else 1
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_related = common_groups_stat[start_idx:end_idx]
            
            result += f"\n🔗 关联用户 ({common_groups_stat_count}) - 第 {page}/{total_pages} 页\n\n"
            
            if page_related:
                for i, related_user in enumerate(page_related, start=start_idx + 1):
                    related_user_id = related_user.get('user_id', '')
                    related_first_name = related_user.get('first_name', '')
                    related_last_name = related_user.get('last_name', '')
                    related_username = related_user.get('username', '')
                    is_user_active = related_user.get('is_user_active', True)
                    
                    # 构建用户名显示
                    name_parts = []
                    if related_first_name:
                        name_parts.append(related_first_name)
                    if related_last_name:
                        name_parts.append(related_last_name)
                    display_name = ' '.join(name_parts) if name_parts else '未知用户'
                    
                    # HTML转义
                    display_name_escaped = display_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    
                    # 如果用户活跃且有用户名，显示为链接
                    if is_user_active and related_username:
                        user_link = f"https://t.me/{related_username}"
                        result += f"{i}. <a href='{user_link}'>{display_name_escaped}</a>\n"
                    else:
                        # 用户失效或无用户名，不显示链接
                        result += f"{i}. {display_name_escaped}\n"
            else:
                result += "  暂无关联用户\n"
        
        # 创建内联按钮
        buttons = []
        
        # 第一行：群组/发言/关联用户切换按钮
        row1 = []
        if view == 'groups':
            row1.append(Button.inline('✅ 群组', f'view_groups_{user_id}_1'))
            row1.append(Button.inline('发言', f'view_messages_{user_id}_1'))
        elif view == 'messages':
            row1.append(Button.inline('群组', f'view_groups_{user_id}_1'))
            row1.append(Button.inline('✅ 发言', f'view_messages_{user_id}_1'))
        elif view == 'related':
            row1.append(Button.inline('群组', f'view_groups_{user_id}_1'))
            row1.append(Button.inline('发言', f'view_messages_{user_id}_1'))
        
        # 只有当功能开启、有关联用户且用户是VIP时才显示关联用户按钮
        if config.SHOW_RELATED_USERS and common_groups_stat_count > 0 and is_vip:
            if view == 'related':
                row1.append(Button.inline('✅ 关联', f'view_related_{user_id}_1'))
            else:
                row1.append(Button.inline('关联', f'view_related_{user_id}_1'))
        
        buttons.append(row1)
        
        # 第二行：分页按钮
        row2 = []
        if view == 'groups':
            groups = user_data.get('groups', [])
            total_items = len(groups)
        elif view == 'messages':
            messages = user_data.get('messages', [])
            total_items = len(messages)
        elif view == 'related':
            common_groups_stat = user_data.get('commonGroupsStat', [])
            total_items = len(common_groups_stat)
        
        total_pages = (total_items + items_per_page - 1) // items_per_page if total_items > 0 else 1
        page = max(1, min(page, total_pages))
        
        if page > 1:
            row2.append(Button.inline('⬅️ 上一页', f'view_{view}_{user_id}_{page-1}'))
        else:
            row2.append(Button.inline('🔒 上一页', f'noop'))
        
        row2.append(Button.inline(f'{page}/{total_pages}', f'noop'))
        
        if page < total_pages:
            row2.append(Button.inline('下一页 ➡️', f'view_{view}_{user_id}_{page+1}'))
        else:
            row2.append(Button.inline('下一页 🔒', f'noop'))
        
        buttons.append(row2)
        
        # 第三行：返回个人中心
        buttons.append([Button.inline('« 返回个人中心', 'cmd_balance')])
        
        return result, buttons
    
    async def _build_personal_center(self, user_id: int):
        """构建个人中心消息与按钮（统一模板）"""
        # 基础数据
        balance = await self.db.get_balance(user_id)
        checkin_info = await self.db.get_checkin_info(user_id)
        invite_stats = await self.db.get_invitation_stats(user_id)
        query_cost = float(await self.db.get_config('query_cost', '1'))
        
        # VIP信息
        vip_display = await self.vip_module.get_vip_display_info(user_id) if self.vip_module else "👤 <b>用户类型：</b>普通用户"
        
        # 文本格式化
        balance_str = f'{int(balance)}' if balance == int(balance) else f'{balance:.2f}'
        checkin_rewards = checkin_info.get("total_rewards", 0)
        checkin_rewards_str = f'{int(checkin_rewards)}' if checkin_rewards == int(checkin_rewards) else f'{checkin_rewards:.2f}'
        invite_rewards = invite_stats.get("total_rewards", 0)
        invite_rewards_str = f'{int(invite_rewards)}' if invite_rewards == int(invite_rewards) else f'{invite_rewards:.2f}'
        
        # 个人中心消息
        message = (
            f'🧘‍♀️ <b>个人中心</b>\n\n'
            f'{vip_display}\n\n'
            f'💰 <b>账户余额</b>\n'
            f'当前余额: <code>{balance_str} 积分</code>\n'
            f'可查询次数: <code>{int(balance / query_cost)}</code> 次\n\n'
            f'📊 <b>统计信息</b>\n'
            f'累计签到: <code>{checkin_info.get("total_days", 0)}</code> 天\n'
            f'签到奖励: <code>{checkin_rewards_str} 积分</code>\n'
            f'邀请人数: <code>{invite_stats.get("total_invites", 0)}</code> 人\n'
            f'邀请奖励: <code>{invite_rewards_str} 积分</code>\n\n'
            f'💡 提示: 每次查询消耗 <code>{int(query_cost)}</code> 积分'
        )
        
        # 按钮（并列：充值积分 + 购买VIP）
        buttons = [
            [
                Button.inline('💳 充值积分', 'recharge_start'),
                Button.inline('💎 购买VIP', 'vip_menu')
            ],
            [
                Button.inline('« 返回主菜单', 'cmd_back_to_main')
            ]
        ]
        
        return message, buttons
    
    async def _build_main_menu(self, user_id: int):
        """构建主菜单消息与按钮"""
        # 获取用户余额
        balance = await self.db.get_balance(user_id)
        balance_str = f'{int(balance)}' if balance == int(balance) else f'{balance:.2f}'
        
        # 获取查询费用
        query_cost = float(await self.db.get_config('query_cost', '1'))
        cost_str = f'{int(query_cost)}' if query_cost == int(query_cost) else f'{query_cost:.2f}'
        
        # 生成邀请链接
        invite_link = ''
        if self.invite_module:
            invite_link = self.invite_module.get_invite_link(user_id)
        
        # 创建分享邀请文本
        bot_username = (await self.client.get_me()).username
        share_text = f'🎁 推荐一个超好用的 TG 用户查询 Bot！\n\n✨ 功能特色：\n• 查询用户详细信息\n• 每日签到领积分\n• 邀请好友有奖励\n\n👉 点击我的专属邀请链接注册：\n{invite_link}\n\n💰 通过邀请链接注册，你我都能获得积分奖励！'
        
        # 创建内联按钮
        inline_buttons = [
            [
                Button.inline('🎁 每日签到', 'cmd_checkin'),
                Button.inline('🧘‍♀️ 个人中心', 'cmd_balance'),
            ],
            [
                Button.inline('🌟 账号充值', 'cmd_recharge_menu'),
            ],
            [
                Button.switch_inline('🎁 邀请好友获得积分', share_text, same_peer=False)
            ],
            [
                Button.inline('🔽 隐藏菜单', 'cmd_hide_keyboard')
            ]
        ]
        
        # 主菜单消息
        message = (
            f'👋 <b>欢迎使用 Telegram 用户查询 Bot！</b>\n\n'
            f'🧘‍♀️ <b>您的信息</b>\n'
            f'• 用户ID: <code>{user_id}</code>\n'
            f'• 当前余额: <code>{balance_str} 积分</code>\n\n'
            f'🎁 <b>邀请好友</b>\n'
            f'邀请好友注册可获得奖励！\n'
            f'您的专属邀请链接：\n'
            f'<code>{invite_link}</code>\n\n'
            f'🔍 <b>查询方法</b>\n'
            f'<i>直接发送用户名或ID即可查询（消耗 {cost_str} 积分）</i>\n'
            f'示例：<code>username</code> 或 <code>@username</code> 或 <code>123456789</code>\n\n'
        )
        
        return message, inline_buttons
    
    def _register_handlers(self):
        """注册所有事件处理器"""
        
        @self.client.on(events.NewMessage(pattern=r'^/start'))
        async def start_handler(event):
            """处理 /start 命令（支持邀请参数）"""
            async with self.semaphore:
                # 获取用户信息
                sender = await event.get_sender()
                user_info = self._format_user_log(sender)
                
                # 检查是否带有邀请参数
                text = event.text.strip()
                parts = text.split()
                referral_code = parts[1] if len(parts) > 1 else None
                
                # 如果有邀请码，处理邀请逻辑
                if referral_code and self.invite_module:
                    await self.invite_module.process_start_with_referral(event, referral_code)
                
                # 构建并发送主菜单
                message, buttons = await self._build_main_menu(event.sender_id)
                await event.respond(message, buttons=buttons, parse_mode='html')
                logger.info(f"用户 {user_info} 启动了Bot")
        
        @self.client.on(events.InlineQuery())
        async def inline_query_handler(event):
            """处理内联查询（用于分享邀请链接）"""
            try:
                query_text = event.text.strip()
                
                # 如果查询文本包含邀请链接，说明是分享邀请
                if 'start=' in query_text or '邀请' in query_text or 'Bot' in query_text:
                    # 创建分享结果
                    builder = event.builder
                    
                    # 提取邀请链接（如果有）
                    invite_link = ''
                    for line in query_text.split('\n'):
                        if 't.me/' in line and 'start=' in line:
                            invite_link = line.strip()
                            break
                    
                    result = builder.article(
                        title='🎁 邀请好友获得积分',
                        description='点击分享给好友，你我都能获得积分奖励！',
                        text=query_text,
                        link_preview=True
                    )
                    
                    await event.answer([result], cache_time=0)
                else:
                    # 其他查询不处理
                    await event.answer([])
                    
            except Exception as e:
                logger.error(f"处理内联查询失败: {e}")
                await event.answer([])
        
        @self.client.on(events.CallbackQuery(pattern=r'^cmd_'))
        async def command_button_handler(event):
            """处理快捷命令按钮"""
            try:
                data = event.data.decode('utf-8')
                command = data.replace('cmd_', '')
                
                if command == 'checkin':
                    # 执行签到
                    sender = await event.get_sender()
                    user_info = self._format_user_log(sender)
                    
                    success, reward, message = await self.db.checkin(event.sender_id)
                    
                    if success:
                        checkin_info = await self.db.get_checkin_info(event.sender_id)
                        balance = await self.db.get_balance(event.sender_id)
                        
                        reward_str = f'{int(reward)}' if reward == int(reward) else f'{reward:.2f}'
                        total_rewards_str = f'{int(checkin_info["total_rewards"])}' if checkin_info["total_rewards"] == int(checkin_info["total_rewards"]) else f'{checkin_info["total_rewards"]:.2f}'
                        balance_str = f'{int(balance)}' if balance == int(balance) else f'{balance:.2f}'
                        
                        await event.answer('✅ 签到成功！', alert=False)
                        await event.respond(
                            f'✅ 签到成功！获得 {reward_str} 积分\n\n'
                            f'💰 当前余额: `{balance_str} 积分`\n'
                            f'📅 累计签到: `{checkin_info["total_days"]}` 天\n'
                            f'🎁 累计奖励: `{total_rewards_str} 积分`',
                    parse_mode='markdown'
                )
                        logger.info(f"用户 {user_info} 通过按钮签到成功，获得 {int(reward)} 积分")
                    else:
                        checkin_info = await self.db.get_checkin_info(event.sender_id)
                        balance = await self.db.get_balance(event.sender_id)
                        
                        balance_str = f'{int(balance)}' if balance == int(balance) else f'{balance:.2f}'
                        today_reward_str = f'{int(checkin_info["today_reward"])}' if checkin_info["today_reward"] == int(checkin_info["today_reward"]) else f'{checkin_info["today_reward"]:.2f}'
                        
                        await event.answer('⚠️ 今天已经签到过了', alert=True)
                        await event.respond(
                            f'⚠️ {message}\n\n'
                            f'💰 当前余额: `{balance_str} 积分`\n'
                            f'📅 累计签到: `{checkin_info["total_days"]}` 天\n'
                            f'🎁 今日奖励: `{today_reward_str} 积分`',
                            parse_mode='markdown'
                        )
                
                elif command == 'balance':
                    # 查看余额（个人中心）
                    await event.answer()
                    message, buttons = await self._build_personal_center(event.sender_id)
                    await event.edit(message, buttons=buttons, parse_mode='html')
                
                elif command == 'back_to_main':
                    # 返回主菜单
                    await event.answer()
                    message, buttons = await self._build_main_menu(event.sender_id)
                    await event.edit(message, buttons=buttons, parse_mode='html')
                
                elif command == 'recharge_menu':
                    # 显示账号充值菜单
                    await event.answer()
                    
                    # 获取实际配置
                    from exchange import exchange_manager
                    
                    # 获取VIP价格（积分）
                    vip_price_points = float(await self.db.get_config('vip_monthly_price', '200'))
                    # 转换为USDT
                    vip_price_usdt = await exchange_manager.points_to_usdt(vip_price_points)
                    
                    # 获取USDT汇率（1 USDT = X 积分）
                    usdt_rate = await exchange_manager.get_usdt_rate()
                    
                    # 计算示例：100 USDT能买多少积分
                    example_usdt = 100
                    example_points = example_usdt * usdt_rate
                    
                    # 格式化价格显示
                    points_per_usdt = f'{usdt_rate:.1f}' if usdt_rate != int(usdt_rate) else f'{int(usdt_rate)}'
                    vip_usdt_str = f'{vip_price_usdt:.1f}' if vip_price_usdt != int(vip_price_usdt) else f'{int(vip_price_usdt)}'
                    example_points_str = f'{example_points:.0f}' if example_points == int(example_points) else f'{example_points:.1f}'
                    
                    message = (
                        f'🛍 <b>价格介绍</b>\n'
                        f'1. 积分价格为 {points_per_usdt} 积分/USDT\n'
                        f'2. 会员价格为 {vip_usdt_str} USDT/月\n'
                        f'3. 充值成功系统自动到账\n\n'
                        f'⚠️ <b>注意事项：</b>\n'
                        f'1. 因用户自己选错充值方式导致的纠纷一律不予处理\n'
                        f'2. 充值通道为USDT TRC20\n'
                        f'3. 转账金额必须完全对应，否则会充值失败\n'
                        f'4. 注意部分交易所存在扣手续费问题，导致实际上链金额错误\n\n'
                        f'━━━━━━━━━━━━━━━━━━\n\n'
                        f'🟢    <b>充值积分：</b>{example_usdt} USDT\n'
                        f'├─  到账积分：{example_points_str} 积分\n'
                        f'└─  包含赠送：0 积分\n\n'
                        f'⭐️    <b>充值会员：</b>{vip_usdt_str} USDT\n'
                        f'├─  到账会员：30 天\n'
                        f'└─  包含赠送：0 天\n\n'
                        f'💡 <b>请选择充值类型：</b>'
                    )
                    
                    buttons = [
                        [Button.inline('🟢 充值积分', 'cmd_buy_points')],
                        [Button.inline('⭐️ 充值会员', 'cmd_buy_vip')],
                        [Button.inline('🔙 返回', 'cmd_back_to_start')]
                    ]
                    
                    await event.edit(message, buttons=buttons, parse_mode='html')
                
                elif command == 'buy_points':
                    # 充值积分 - 显示充值选项
                    await event.answer()
                    
                    # 检查充值功能是否启用
                    if not config.RECHARGE_WALLET_ADDRESS:
                        await event.answer('❌ 充值功能暂未开放', alert=True)
                        return
                    
                    # 检查是否有未完成的订单
                    active_order = await self.db.get_active_order(event.sender_id)
                    if active_order:
                        await event.answer('⚠️ 您有未完成的订单', alert=True)
                        return
                    
                    # 显示充值选项
                    buttons = [
                        [Button.inline('💵 USDT充值', 'recharge_usdt')],
                        [Button.inline('💎 TRX充值', 'recharge_trx')],
                        [Button.inline('🔙 返回', 'cmd_recharge_menu')]
                    ]
                    
                    # 获取最小充值金额
                    min_amount = float(await self.db.get_config('recharge_min_amount', '10'))
                    
                    await event.edit(
                        '💳 <b>选择充值方式</b>\n\n'
                        f'最小充值金额: <code>{min_amount}</code>\n\n'
                        '请选择您要使用的充值币种：',
                        buttons=buttons,
                        parse_mode='html'
                    )
                
                elif command == 'buy_vip':
                    # 开通VIP - 显示VIP购买菜单
                    await event.answer()
                    if self.vip_module:
                        await self.vip_module.show_vip_purchase_menu(event, is_edit=True)
                    else:
                        await event.answer('❌ VIP功能暂不可用', alert=True)
                
                elif command == 'buy_usdt':
                    # 充值USDT - 暂未开放
                    await event.answer(
                        '⚠️ USDT充值功能正在完善中\n\n'
                        '请选择"充值积分"或"充值会员"进行充值',
                        alert=True
                    )
                
                elif command == 'hide_keyboard':
                    # 隐藏底部键盘按钮
                    await event.answer('✅ 菜单已隐藏')
                    await event.respond(
                        '✅ 底部菜单已隐藏\n\n'
                        '💡 需要时可以随时发送 /start 重新显示菜单',
                        buttons=Button.clear()
                    )
                
                elif command == 'back_to_start':
                    # 返回开始菜单
                    await event.answer()
                    await event.delete()
                
            except Exception as e:
                logger.error(f"命令按钮处理失败: {e}")
                try:
                    await event.answer('❌ 处理失败', alert=True)
                except:
                    pass
        
        @self.client.on(events.NewMessage(pattern=r'^/text\s+(.+)'))
        async def text_search_handler(event):
            """处理文本搜索命令"""
            async with self.semaphore:
                # 提取搜索关键词
                import re
                match = re.match(r'^/text\s+(.+)', event.text)
                if not match:
                    await event.respond('❌ 请输入搜索关键词\n\n用法: /text 关键词')
                    return
                
                search_text = match.group(1).strip()
                
                # 检查VIP配额或余额
                vip_quota = await self.vip_module.check_and_use_daily_quota(event.sender_id, 'text')
                search_cost = float(await self.db.get_config('text_search_cost', '1'))
                current_balance = await self.db.get_balance(event.sender_id)
                
                use_vip_quota = vip_quota['can_use_quota']
                
                # 如果不能使用VIP配额，检查积分余额
                if not use_vip_quota and current_balance < search_cost:
                    vip_msg = ""
                    if vip_quota['is_vip']:
                        vip_msg = f"💎 VIP免费查询已用完 ({vip_quota['total']} 次/天)\n\n"
                    
                    await event.respond(
                        f'❌ 余额不足\n\n'
                        f'{vip_msg}'
                        f'💰 当前余额: `{current_balance:.2f} 积分`\n'
                        f'💳 需要: `{search_cost:.2f} 积分`\n\n'
                        f'📝 请使用 /qd 签到获取积分，或开通VIP享受每日免费查询',
                        parse_mode='markdown'
                    )
                    return
                
                # 发送处理中消息
                processing_msg = await event.respond(f'🔍 正在搜索: `{search_text}`...', parse_mode='markdown')
                
                # 先调用API获取总数
                api_result = await self._search_text_api(search_text)
                
                if not api_result or not api_result.get('success'):
                    await processing_msg.edit(
                        '❌ 搜索失败\n\n'
                        '可能的原因：\n'
                        '• API服务异常\n'
                        '• 搜索超时\n\n'
                        '💰 余额未扣除\n\n'
                        '请稍后重试',
                        parse_mode='html'
                    )
                    sender = await event.get_sender()
                    user_info = self._format_user_log(sender)
                    logger.warning(f"用户 {user_info} 搜索 '{search_text}' 失败（未扣费）")
                    return
                
                api_total = api_result.get('data', {}).get('total', 0)
                
                # 检查数据库缓存
                db_cache = await self.db.get_text_search_cache(search_text)
                db_total = db_cache['total'] if db_cache else None
                
                # 判断是否需要更新缓存
                if db_total is not None and db_total == api_total:
                    # 使用数据库缓存
                    logger.info(f"使用数据库缓存: 关键词='{search_text}', 总数={db_total}")
                    result = json.loads(db_cache['results_json'])
                    data_source = "💾 数据库"
                else:
                    # 更新数据库缓存
                    logger.info(f"更新数据库缓存: 关键词='{search_text}', API总数={api_total}, DB总数={db_total}")
                    results_json = json.dumps(api_result, ensure_ascii=False)
                    await self.db.save_text_search_cache(search_text, api_total, results_json)
                    result = api_result
                    data_source = "🌐 API"
                
                # 缓存到内存（用于翻页）
                cache_key = f"text_{search_text}_{event.sender_id}"
                self.text_search_cache[cache_key] = result
                
                # 限制内存缓存大小
                if len(self.text_search_cache) > 50:
                    keys_to_remove = list(self.text_search_cache.keys())[:25]
                    for key in keys_to_remove:
                        del self.text_search_cache[key]
                
                # 格式化结果
                formatted, buttons = self._format_text_search_results(result, page=1, search_cost=search_cost, use_vip=use_vip_quota, vip_remaining=vip_quota['remaining'])
                
                # 记录关键词查询日志
                try:
                    await self.db.log_text_query(search_text, event.sender_id, from_cache=bool(db_cache))
                except Exception as e:
                    logger.error(f"记录关键词查询日志失败: {e}")
                
                if formatted and buttons:
                    # 扣除搜索费用（如果使用VIP配额则不扣费）
                    cost_msg = ""
                    if use_vip_quota:
                        cost_msg = f"💎 VIP免费查询 (剩余 {vip_quota['remaining']} 次)"
                    else:
                        deduct_success = await self.db.change_balance(
                            event.sender_id,
                            -search_cost,
                            'text_search',
                            f'搜索关键词: {search_text}'
                        )
                        
                        if not deduct_success:
                            await processing_msg.edit('❌ 扣费失败，请稍后重试')
                            return
                        cost_msg = f"💰 消耗 {search_cost:.0f} 积分"
                    
                    await processing_msg.edit(formatted, buttons=buttons, parse_mode='html', link_preview=False)
                    
                    sender = await event.get_sender()
                    user_info = self._format_user_log(sender)
                    new_balance = await self.db.get_balance(event.sender_id)
                    logger.info(f"用户 {user_info} 搜索关键词 '{search_text}' ({data_source})，{cost_msg}，余额: {new_balance:.2f}")
                else:
                    await processing_msg.edit('❌ 未找到匹配的消息')
        
        @self.client.on(events.NewMessage(pattern='/qd'))
        async def checkin_handler(event):
            """处理签到命令"""
            async with self.semaphore:
                sender = await event.get_sender()
                user_info = self._format_user_log(sender)
                
                # 执行签到
                success, reward, message = await self.db.checkin(event.sender_id)
                
                if success:
                    # 获取签到信息
                    checkin_info = await self.db.get_checkin_info(event.sender_id)
                    balance = await self.db.get_balance(event.sender_id)
                    
                    # 格式化整数奖励
                    reward_str = f'{int(reward)}' if reward == int(reward) else f'{reward:.2f}'
                    total_rewards_str = f'{int(checkin_info["total_rewards"])}' if checkin_info["total_rewards"] == int(checkin_info["total_rewards"]) else f'{checkin_info["total_rewards"]:.2f}'
                    balance_str = f'{int(balance)}' if balance == int(balance) else f'{balance:.2f}'
                    
                    await event.respond(
                        f'✅ 签到成功！获得 {reward_str} 积分\n\n'
                        f'💰 当前余额: `{balance_str} 积分`\n'
                        f'📅 累计签到: `{checkin_info["total_days"]}` 天\n'
                        f'🎁 累计奖励: `{total_rewards_str} 积分`',
                        parse_mode='markdown'
                    )
                    logger.info(f"用户 {user_info} 签到成功，获得 {int(reward)} 积分")
                else:
                    # 今天已签到
                    checkin_info = await self.db.get_checkin_info(event.sender_id)
                    balance = await self.db.get_balance(event.sender_id)
                    
                    # 格式化整数
                    balance_str = f'{int(balance)}' if balance == int(balance) else f'{balance:.2f}'
                    today_reward_str = f'{int(checkin_info["today_reward"])}' if checkin_info["today_reward"] == int(checkin_info["today_reward"]) else f'{checkin_info["today_reward"]:.2f}'
                    
                    await event.respond(
                        f'⚠️ {message}\n\n'
                        f'💰 当前余额: `{balance_str} 积分`\n'
                        f'📅 累计签到: `{checkin_info["total_days"]}` 天\n'
                        f'🎁 今日奖励: `{today_reward_str} 积分`',
                    parse_mode='markdown'
                    )
        
        @self.client.on(events.NewMessage(pattern='/balance'))
        async def balance_handler(event):
            """处理余额查询命令（个人中心）"""
            async with self.semaphore:
                message, buttons = await self._build_personal_center(event.sender_id)
                await event.respond(message, buttons=buttons, parse_mode='html')
        
        @self.client.on(events.NewMessage(pattern='/buyvip'))
        async def buyvip_handler(event):
            """处理购买VIP命令"""
            async with self.semaphore:
                # 检查充值功能是否启用
                if not config.RECHARGE_WALLET_ADDRESS:
                    await event.respond('❌ VIP购买功能暂未开放')
                    return
                
                # 检查VIP模块是否可用
                if not self.vip_module:
                    await event.respond('❌ VIP购买功能暂未开放')
                    return
                
                # 显示VIP购买菜单
                await self.vip_module.show_vip_purchase_menu(event, is_edit=False)
                
                # 记录日志
                sender = await event.get_sender()
                user_info = self._format_user_log(sender)
                logger.info(f"用户 {user_info} 使用了 /buyvip 命令")
        
        @self.client.on(events.CallbackQuery(pattern=r'^(view_|noop)'))
        async def callback_handler(event):
            """处理内联按钮回调 - 优化性能版"""
            # 立即响应，避免超时
            try:
                data = event.data.decode('utf-8')
                
                # 忽略无操作按钮
                if data == 'noop':
                    await event.answer('已在边界位置', alert=False)
                    return
                
                # 解析回调数据: view_视图_用户ID_页码
                parts = data.split('_', 3)  # 限制分割次数提高性能
                if len(parts) < 4:
                    await event.answer('数据格式错误', alert=True)
                    return
                
                _, view, user_id, page_str = parts
                
                try:
                    page = int(page_str)
                except ValueError:
                    await event.answer('页码错误', alert=True)
                    return
                
                # 从缓存获取数据（快速查找）
                cache_key = f"user_{user_id}"
                query_result = self.query_cache.get(cache_key)
                
                if not query_result:
                    await event.answer('⚠️ 查询已过期，请重新查询', alert=True)
                    return
                
                # 先响应回调，避免超时
                await event.answer()
                
                # 异步处理格式化和编辑（不阻塞）
                async with self.semaphore:
                    try:
                        # 获取用户VIP状态
                        vip_info = await self.db.get_user_vip_info(event.sender_id)
                        is_vip = vip_info['is_vip']
                        
                        # 格式化新页面
                        formatted, buttons = self._format_user_info(query_result, view=view, page=page, is_vip=is_vip)
                        
                        if formatted and buttons:
                            # 使用try-except保护编辑操作
                            try:
                                await event.edit(formatted, buttons=buttons, parse_mode='html', link_preview=False)
                                logger.debug(f"页面已更新: {view} - 第{page}页")
                            except Exception as edit_error:
                                # 消息可能太相似，Telegram拒绝编辑
                                logger.debug(f"消息编辑被跳过: {edit_error}")
                        else:
                            logger.error("格式化失败")
                    except Exception as e:
                        logger.error(f"回调处理异常: {e}")
                        
            except Exception as e:
                logger.error(f"回调处理错误: {e}")
                try:
                    await event.answer('❌ 处理失败', alert=True)
                except:
                    pass
        
        @self.client.on(events.CallbackQuery(pattern=r'^text_search_'))
        async def text_search_callback_handler(event):
            """处理文本搜索翻页回调"""
            try:
                data = event.data.decode('utf-8')
                # 解析: text_search_关键词_页码
                parts = data.replace('text_search_', '', 1).rsplit('_', 1)
                
                if len(parts) != 2:
                    await event.answer('数据格式错误', alert=True)
                    return
                
                search_text, page_str = parts
                
                try:
                    page = int(page_str)
                except ValueError:
                    await event.answer('页码错误', alert=True)
                    return
                
                # 从缓存获取搜索结果
                cache_key = f"text_{search_text}_{event.sender_id}"
                result = self.text_search_cache.get(cache_key)
                
                if not result:
                    await event.answer('⚠️ 搜索已过期，请重新搜索', alert=True)
                    return
                
                await event.answer()
                
                # 格式化新页面
                formatted, buttons = self._format_text_search_results(result, page=page)
                
                if formatted and buttons:
                    try:
                        await event.edit(formatted, buttons=buttons, parse_mode='html', link_preview=False)
                        logger.debug(f"文本搜索翻页: {search_text} - 第{page}页")
                    except Exception as edit_error:
                        logger.debug(f"消息编辑被跳过: {edit_error}")
                else:
                    logger.error("文本搜索格式化失败")
                    
            except Exception as e:
                logger.error(f"文本搜索回调处理错误: {e}")
                try:
                    await event.answer('❌ 处理失败', alert=True)
                except:
                    pass
        
        @self.client.on(events.NewMessage())
        async def text_search_reply_handler(event):
            """处理关键词搜索的引用回复"""
            # 检查是否是回复消息
            if not event.is_reply:
                return
            
            # 获取回复的消息
            try:
                reply_msg = await event.get_reply_message()
                if not reply_msg or reply_msg.id not in self.pending_text_search:
                    return
            except:
                return
            
            # 提取搜索关键词
            search_text = event.text.strip()
            
            if not search_text:
                await event.respond('❌ 请输入搜索关键词')
                return
            
            # 移除等待状态
            self.pending_text_search.discard(reply_msg.id)
            
            # 使用与 /text 命令相同的逻辑
            async with self.semaphore:
                # 检查VIP配额或余额
                vip_quota = await self.vip_module.check_and_use_daily_quota(event.sender_id, 'text')
                search_cost = float(await self.db.get_config('text_search_cost', '1'))
                current_balance = await self.db.get_balance(event.sender_id)
                
                use_vip_quota = vip_quota['can_use_quota']
                
                # 如果不能使用VIP配额，检查积分余额
                if not use_vip_quota and current_balance < search_cost:
                    vip_msg = ""
                    if vip_quota['is_vip']:
                        vip_msg = f"💎 VIP免费查询已用完 ({vip_quota['total']} 次/天)\n\n"
                    
                    await event.respond(
                        f'❌ 余额不足\n\n'
                        f'{vip_msg}'
                        f'💰 当前余额: `{current_balance:.2f} 积分`\n'
                        f'💳 需要: `{search_cost:.2f} 积分`\n\n'
                        f'📝 请使用 /qd 签到获取积分，或开通VIP享受每日免费查询',
                        parse_mode='markdown'
                    )
                    return
                
                # 发送处理中消息
                processing_msg = await event.respond(f'🔍 正在搜索: `{search_text}`...', parse_mode='markdown')
                
                # 先调用API获取总数
                api_result = await self._search_text_api(search_text)
                
                if not api_result or not api_result.get('success'):
                    await processing_msg.edit(
                        '❌ 搜索失败\n\n'
                        '可能的原因：\n'
                        '• API服务异常\n'
                        '• 搜索超时\n\n'
                        '💰 余额未扣除\n\n'
                        '请稍后重试',
                        parse_mode='html'
                    )
                    sender = await event.get_sender()
                    user_info = self._format_user_log(sender)
                    logger.warning(f"用户 {user_info} 通过回复搜索 '{search_text}' 失败（未扣费）")
                    return
                
                api_total = api_result.get('data', {}).get('total', 0)
                
                # 检查数据库缓存
                db_cache = await self.db.get_text_search_cache(search_text)
                db_total = db_cache['total'] if db_cache else None
                
                # 判断是否需要更新缓存
                if db_total is not None and db_total == api_total:
                    # 使用数据库缓存
                    logger.info(f"使用数据库缓存: 关键词='{search_text}', 总数={db_total}")
                    result = json.loads(db_cache['results_json'])
                    data_source = "💾 数据库"
                else:
                    # 更新数据库缓存
                    logger.info(f"更新数据库缓存: 关键词='{search_text}', API总数={api_total}, DB总数={db_total}")
                    results_json = json.dumps(api_result, ensure_ascii=False)
                    await self.db.save_text_search_cache(search_text, api_total, results_json)
                    result = api_result
                    data_source = "🌐 API"
                
                # 缓存到内存（用于翻页）
                cache_key = f"text_{search_text}_{event.sender_id}"
                self.text_search_cache[cache_key] = result
                
                # 限制内存缓存大小
                if len(self.text_search_cache) > 50:
                    keys_to_remove = list(self.text_search_cache.keys())[:25]
                    for key in keys_to_remove:
                        del self.text_search_cache[key]
                
                # 格式化结果
                formatted, buttons = self._format_text_search_results(result, page=1, search_cost=search_cost, use_vip=use_vip_quota, vip_remaining=vip_quota['remaining'])
                
                # 记录关键词查询日志
                try:
                    await self.db.log_text_query(search_text, event.sender_id, from_cache=bool(db_cache))
                except Exception as e:
                    logger.error(f"记录关键词查询日志失败: {e}")
                
                if formatted and buttons:
                    # 扣除搜索费用（如果使用VIP配额则不扣费）
                    cost_msg = ""
                    if use_vip_quota:
                        cost_msg = f"💎 VIP免费查询 (剩余 {vip_quota['remaining']} 次)"
                    else:
                        deduct_success = await self.db.change_balance(
                            event.sender_id,
                            -search_cost,
                            'text_search',
                            f'搜索关键词: {search_text}'
                        )
                        
                        if not deduct_success:
                            await processing_msg.edit('❌ 扣费失败，请稍后重试')
                            return
                        cost_msg = f"💰 消耗 {search_cost:.0f} 积分"
                    
                    await processing_msg.edit(formatted, buttons=buttons, parse_mode='html', link_preview=False)
                    
                    sender = await event.get_sender()
                    user_info = self._format_user_log(sender)
                    new_balance = await self.db.get_balance(event.sender_id)
                    logger.info(f"用户 {user_info} 通过回复搜索关键词 '{search_text}' ({data_source})，{cost_msg}，余额: {new_balance:.2f}")
                else:
                    await processing_msg.edit('❌ 未找到匹配的消息')
        
        @self.client.on(events.NewMessage())
        async def query_handler(event):
            """处理查询请求 - 优先使用数据库"""
            # 跳过命令消息
            if event.text and event.text.startswith('/'):
                return
            
            if not event.text:
                return
            
            # 跳过键盘按钮消息
            if event.text.strip() in ['🏠 开始', '🧘‍♀️ 个人中心', '💳 购买积分', '💎 购买VIP', '🔍 关键词查询', '📞 联系客服']:
                return
            
            # 跳过回复消息（避免管理员回复通知时触发查询）
            if event.is_reply:
                return
            
            # 跳过包含换行符的消息（通知内容可能包含多行）
            if '\n' in event.text.strip():
                return
            
            # 跳过包含HTML标签的消息
            if '<' in event.text or '>' in event.text:
                return
            
            # **重要：检查管理员是否正在进行其他操作（如广播、设置客服等）**
            if self.admin_module and event.sender_id in self.admin_module.admin_state:
                return
            
            # 验证用户名格式（基本验证）
            text = event.text.strip()
            # 移除可能的URL前缀
            if text.startswith('http') and 't.me/' not in text.lower():
                return
            
            async with self.semaphore:
                # 解析用户名
                username = self._parse_username(event.text)
                
                # 严格验证用户名格式
                if not username:
                    return
                
                # 用户名只能包含字母、数字、下划线，长度4-32
                # 或者是纯数字ID
                if not username.isdigit():
                    if not re.match(r'^[a-zA-Z0-9_]{4,32}$', username):
                        await event.respond('❌ 无效的用户名格式\n\n用户名应为 4-32 位，只能包含字母、数字和下划线')
                        return
                
                # 检查VIP配额或余额
                vip_quota = await self.vip_module.check_and_use_daily_quota(event.sender_id, 'user')
                query_cost = float(await self.db.get_config('query_cost', '1'))
                current_balance = await self.db.get_balance(event.sender_id)
                
                use_vip_quota = vip_quota['can_use_quota']
                
                # 如果不能使用VIP配额，检查积分余额
                if not use_vip_quota and current_balance < query_cost:
                    vip_msg = ""
                    if vip_quota['is_vip']:
                        vip_msg = f"💎 VIP免费查询已用完 ({vip_quota['total']} 次/天)\n\n"
                    
                    await event.respond(
                        f'❌ 余额不足\n\n'
                        f'{vip_msg}'
                        f'💰 当前余额: `{current_balance:.2f} 积分`\n'
                        f'💳 需要: `{query_cost:.2f} 积分`\n\n'
                        f'📝 请使用 /qd 签到获取积分，或开通VIP享受每日免费查询',
                        parse_mode='markdown'
                    )
                    return
                
                # 发送处理中消息（不在这里检查隐藏，因为需要等API返回后才知道真实的用户ID）
                processing_msg = await event.respond(f'🔍 正在查询: `{username}`...', parse_mode='markdown')
                
                result = None
                from_db = False
                db_result = None
                
                # 先从数据库查询
                try:
                    db_result = await self.db.get_user_data(username)
                    if db_result:
                        logger.info(f"数据库中找到用户 {username} 缓存")
                except Exception as e:
                    logger.error(f"数据库查询错误: {e}")
                
                # 调用API获取最新数据（用于对比或获取新数据）
                api_result = await self._query_api(username)
                
                # 如果API请求成功
                if api_result and api_result.get('success'):
                    # 如果数据库有缓存，对比数据总数
                    if db_result:
                        db_user_data = db_result.get('data', {})
                        api_user_data = api_result.get('data', {})
                        
                        db_msg_count = db_user_data.get('messageCount', 0)
                        db_groups_count = db_user_data.get('groupsCount', 0)
                        api_msg_count = api_user_data.get('messageCount', 0)
                        api_groups_count = api_user_data.get('groupsCount', 0)
                        
                        # 对比数据总数
                        if db_msg_count == api_msg_count and db_groups_count == api_groups_count:
                            # 数据一致，使用数据库缓存
                            result = db_result
                            from_db = True
                            logger.info(f"用户 {username} 数据未变化 (消息:{db_msg_count}, 群组:{db_groups_count})，使用缓存")
                        else:
                            # 数据有更新，使用API数据并更新数据库
                            result = api_result
                            from_db = False
                            logger.info(f"用户 {username} 数据已更新 (消息:{db_msg_count}→{api_msg_count}, 群组:{db_groups_count}→{api_groups_count})，更新数据库")
                            try:
                                await self.db.save_user_data(result)
                                logger.info(f"用户 {username} 新数据已保存到数据库")
                            except Exception as e:
                                logger.error(f"保存到数据库失败: {e}")
                    else:
                        # 数据库没有缓存，使用API数据并保存
                        result = api_result
                        from_db = False
                        logger.info(f"数据库无缓存，从API获取用户 {username} 数据")
                        try:
                            await self.db.save_user_data(result)
                            logger.info(f"用户 {username} 数据已保存到数据库")
                        except Exception as e:
                            logger.error(f"保存到数据库失败: {e}")
                elif db_result:
                    # API请求失败但数据库有缓存，使用缓存数据
                    result = db_result
                    from_db = True
                    logger.warning(f"API请求失败，使用数据库缓存数据 (可能不是最新)")
                
                if result and result.get('success'):
                    # 获取返回的用户信息
                    user_data = result.get('data', {})
                    basic_info = user_data.get('basicInfo', {})
                    returned_user_id = str(basic_info.get('id', user_data.get('userId', '')))
                    returned_username = basic_info.get('username', '')
                    
                    # 检查返回的用户ID或用户名是否被隐藏
                    is_id_hidden = await self.db.is_user_hidden(returned_user_id) if returned_user_id else False
                    is_username_hidden = await self.db.is_user_hidden(returned_username) if returned_username else False
                    
                    if is_id_hidden or is_username_hidden:
                        # 用户被隐藏，不显示数据，不扣费
                        hidden_identifier = returned_username if returned_username else returned_user_id
                        await processing_msg.edit(
                            f'🔒 <b>查询受限</b>\n\n'
                            f'用户 <code>{hidden_identifier}</code> 的数据已被管理员隐藏。\n\n'
                            f'💰 余额未扣除\n'
                            f'💡 如有疑问，请联系管理员。',
                            parse_mode='html'
                        )
                        logger.info(f"用户尝试查询被隐藏的用户: {username} (实际ID: {returned_user_id})")
                        return
                    
                    # 处理关联用户数据的智能缓存
                    user_id = returned_user_id or user_data.get('userId') or basic_info.get('id')
                    if user_id and config.SHOW_RELATED_USERS:
                        try:
                            # 从API返回中获取关联用户数据
                            api_related_count = user_data.get('commonGroupsStatCount', 0)
                            api_related_data = user_data.get('commonGroupsStat', [])
                            
                            # 检查数据库中的关联用户缓存
                            db_related_cache = await self.db.get_related_users_cache(int(user_id))
                            db_related_count = db_related_cache['total'] if db_related_cache else None
                            
                            # 判断是否需要更新缓存
                            if db_related_count is not None and db_related_count == api_related_count:
                                # 使用数据库缓存
                                logger.info(f"使用关联用户数据库缓存: user_id={user_id}, 总数={db_related_count}")
                                cached_related_data = json.loads(db_related_cache['results_json'])
                                # 替换result中的关联用户数据
                                result['data']['commonGroupsStat'] = cached_related_data
                                result['data']['commonGroupsStatCount'] = db_related_count
                            else:
                                # 更新数据库缓存
                                logger.info(f"更新关联用户数据库缓存: user_id={user_id}, API总数={api_related_count}, DB总数={db_related_count}")
                                related_json = json.dumps(api_related_data, ensure_ascii=False)
                                await self.db.save_related_users_cache(int(user_id), api_related_count, related_json)
                        except Exception as e:
                            logger.error(f"处理关联用户缓存失败: {e}")
                    
                    # 缓存结果到内存（用于分页）
                    if user_id:
                        cache_key = f"user_{user_id}"
                        self.query_cache[cache_key] = result
                        
                        # 限制缓存大小（最多保留100个）
                        if len(self.query_cache) > 100:
                            # 删除最旧的50个
                            keys_to_remove = list(self.query_cache.keys())[:50]
                            for key in keys_to_remove:
                                del self.query_cache[key]
                    
                    # 获取查询者信息
                    sender = await event.get_sender()
                    user_info = self._format_user_log(sender)
                    
                    # 获取VIP状态（用于控制关联用户按钮显示）
                    vip_info = await self.db.get_user_vip_info(event.sender_id)
                    is_vip = vip_info['is_vip']
                    
                    # 格式化并发送结果（默认显示群组列表）
                    formatted, buttons = self._format_user_info(result, view='groups', page=1, is_vip=is_vip)
                    if formatted and buttons:
                        # 扣除查询费用（如果使用VIP配额则不扣费）
                        cost_msg = ""
                        if use_vip_quota:
                            cost_msg = f"💎 VIP免费查询 (剩余 {vip_quota['remaining']} 次)"
                        else:
                            deduct_success = await self.db.change_balance(
                                event.sender_id, 
                                -query_cost, 
                                'query', 
                                f'查询用户 {username}'
                            )
                            
                            if not deduct_success:
                                await processing_msg.edit('❌ 扣费失败，请稍后重试')
                                return
                            cost_msg = f"💰 消耗 {query_cost:.0f} 积分"
                        
                        # 禁用链接预览
                        await processing_msg.edit(formatted, buttons=buttons, parse_mode='html', link_preview=False)
                        data_source = "💾 本地数据库" if from_db else "🔄 API实时"
                        new_balance = await self.db.get_balance(event.sender_id)
                        logger.info(f"用户 {user_info} 成功查询了 {username} ({data_source})，{cost_msg}，余额: {new_balance:.2f}")
                        
                        # 记录查询日志
                        try:
                            await self.db.log_query(username, event.sender_id, from_db)
                        except Exception as e:
                            logger.error(f"记录查询日志失败: {e}")
                    else:
                        await processing_msg.edit('❌ 数据解析失败，请稍后重试')
                else:
                    sender = await event.get_sender()
                    user_info = self._format_user_log(sender)
                    balance = await self.db.get_balance(event.sender_id)
                    await processing_msg.edit(
                        f'❌ 查询失败\n\n'
                        f'可能的原因：\n'
                        f'• 用户不存在\n'
                        f'• 用户名错误\n'
                        f'• API服务异常\n\n'
                        f'💰 余额未扣除，当前余额: `{balance:.2f} 积分`\n\n'
                        f'请检查输入是否正确',
                        parse_mode='markdown'
                    )
                    logger.warning(f"用户 {user_info} 查询 {username} 失败（未扣费）")
    
    async def start(self):
        """启动 Bot"""
        logger.info("正在启动 Bot...")
        
        # 连接数据库
        await self.db.connect()
        
        # 初始化汇率（固定汇率从数据库加载）与 API 开关（持久化）
        try:
            from exchange import exchange_manager
            # 先加载固定汇率（若存在则覆盖默认值）
            try:
                usdt_fixed = await self.db.get_config('fixed_rate_usdt_points', '')
                if usdt_fixed:
                    exchange_manager.set_fixed_rate('USDT', float(usdt_fixed))
                trx_fixed = await self.db.get_config('fixed_rate_trx_points', '')
                if trx_fixed:
                    exchange_manager.set_fixed_rate('TRX', float(trx_fixed))
            except Exception as _:
                pass
            use_api_conf = await self.db.get_config('exchange_use_api', '1')
            exchange_manager.enable_api(use_api_conf == '1')
            exchange_manager.clear_cache()
            logger.info(f"汇率API开关已加载: {'启用' if exchange_manager.use_api else '禁用'}")
        except Exception as e:
            logger.error(f"初始化汇率API开关失败: {e}")
        
        # 显示数据库统计
        stats = await self.db.get_statistics()
        logger.info(f"数据库统计: 用户={stats.get('users', 0)}, 群组={stats.get('groups', 0)}, 消息={stats.get('messages', 0)}")
        
        # 启动客户端
        await self.client.start(bot_token=config.BOT_TOKEN)
        
        me = await self.client.get_me()
        self.bot_username = me.username
        logger.info(f"Bot 已启动: @{me.username} (ID: {me.id})")
        
        # 设置Bot命令提示
        from telethon.tl.functions.bots import SetBotCommandsRequest
        from telethon.tl.types import BotCommand, BotCommandScopeDefault, BotCommandScopePeer
        
        # 普通用户命令
        commands = [
            BotCommand(command='start', description='开始'),
        ]
        
        try:
            await self.client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code='zh',
                commands=commands
            ))
            logger.info("✅ Bot命令提示已设置成功")
        except Exception as e:
            logger.error(f"❌ 设置Bot命令提示失败: {e}")
            logger.info("💡 建议手动通过 @BotFather 设置命令列表")
        
        # 为管理员设置额外的命令
        if config.ADMIN_IDS:
            admin_commands = commands + [
                BotCommand(command='a', description='📋 管理员命令中心'),
                BotCommand(command='tj', description='📊 查看数据统计'),
            ]
            
            for admin_id in config.ADMIN_IDS:
                try:
                    await self.client(SetBotCommandsRequest(
                        scope=BotCommandScopePeer(peer=admin_id),
                        lang_code='zh',
                        commands=admin_commands
                    ))
                except Exception as e:
                    logger.warning(f"⚠️ 为管理员 {admin_id} 设置命令失败: {e}")
            
            logger.info(f"✅ 已为 {len(config.ADMIN_IDS)} 位管理员设置专属命令")
        
        # 初始化管理员模块
        if config.ADMIN_IDS:
            from admin import AdminModule
            self.admin_module = AdminModule(self)
            self.admin_module.register_handlers()
            logger.info(f"管理员模块已启动，管理员数量: {len(config.ADMIN_IDS)}")
        else:
            logger.warning("未配置管理员ID，管理员功能已禁用")
        
        # 初始化邀请模块
        from invite import InviteModule
        self.invite_module = InviteModule(self)
        logger.info("邀请模块已启动")
        
        # 初始化充值模块
        from recharge import RechargeModule
        self.recharge_module = RechargeModule(self)
        self.recharge_module.register_handlers()
        await self.recharge_module.start_scanner()
        logger.info("充值模块已启动")
        
        # 初始化VIP模块
        from vip import VIPModule
        self.vip_module = VIPModule(self.client, self.db)
        logger.info("VIP模块已启动")
        
        logger.info("Bot 正在运行，按 Ctrl+C 停止...")
        
        # 保持运行
        await self.client.run_until_disconnected()
    
    async def stop(self):
        """停止 Bot"""
        logger.info("正在停止 Bot...")
        
        # 停止充值扫描器
        if hasattr(self, 'recharge_module') and self.recharge_module:
            await self.recharge_module.stop_scanner()
        
        # 关闭HTTP会话
        if self.http_session:
            await self.http_session.close()
        
        # 关闭数据库
        await self.db.close()
        
        await self.client.disconnect()


async def main():
    """主函数"""
    # 创建 Bot 实例
    bot = TelegramQueryBot()
    
    try:
        # 启动 Bot
        await bot.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.error(f"发生错误: {e}", exc_info=True)
    finally:
        # 清理资源
        await bot.stop()


if __name__ == '__main__':
    # 运行 Bot
    asyncio.run(main())