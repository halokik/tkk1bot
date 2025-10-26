"""
管理员模块 - 提供管理员专用功能
"""
import logging
from telethon import events, Button
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import TelegramQueryBot

import config
from exchange import exchange_manager

logger = logging.getLogger(__name__)


class AdminModule:
    """管理员功能模块"""
    
    def __init__(self, bot_instance: 'TelegramQueryBot'):
        """
        初始化管理员模块
        
        Args:
            bot_instance: Bot实例
        """
        self.bot = bot_instance
        self.client = bot_instance.client
        self.db = bot_instance.db
        
        # 等待通知回复的消息ID集合
        self.pending_notifications = set()
        
        # 等待客服设置回复的消息ID集合
        self.pending_service_set = set()
        
        # 通知计数器（用于生成简短的回调数据）
        self.notification_counter = 0
        
        logger.info(f"管理员模块已加载，管理员ID: {config.ADMIN_IDS}")
    
    def is_admin(self, user_id: int) -> bool:
        """检查用户是否为管理员"""
        return user_id in config.ADMIN_IDS
    
    async def _format_admin_log(self, event):
        """
        格式化管理员信息用于日志输出
        
        Args:
            event: Telethon事件对象
        
        Returns:
            格式化的管理员信息字符串
        """
        try:
            sender = await event.get_sender()
            if not sender:
                return f"管理员 (ID:{event.sender_id})"
            
            # 用户名
            username = f"@{sender.username}" if sender.username else "无用户名"
            
            # 姓名
            name_parts = []
            if hasattr(sender, 'first_name') and sender.first_name:
                name_parts.append(sender.first_name)
            if hasattr(sender, 'last_name') and sender.last_name:
                name_parts.append(sender.last_name)
            name = " ".join(name_parts) if name_parts else "无姓名"
            
            return f"管理员 {name} ({username}, ID:{sender.id})"
        except Exception as e:
            logger.error(f"格式化管理员信息失败: {e}")
            return f"管理员 (ID:{event.sender_id})"
    
    def register_handlers(self):
        """注册管理员事件处理器"""
        
        def _build_help_main():
            """构建管理员命令中心主菜单文本与按钮（统一复用）"""
            help_text = (
                '📋 <b>管理员命令中心</b>\n\n'
                '欢迎使用管理员功能！\n\n'
                '请选择要查看的功能分类：'
            )
            buttons = [
                [
                    Button.inline('📊 统计查询', 'help_stats'),
                    Button.inline('💰 余额管理', 'help_balance'),
                ],
                [
                    Button.inline('⚙️ 系统配置', 'help_config'),
                    Button.inline('🔒 隐藏用户', 'help_hidden'),
                ],
                [
                    Button.inline('💎 VIP管理', 'help_vip'),
                    Button.inline('👨‍💼 客服管理', 'help_service'),
                ],
                [
                    Button.inline('📢 通知功能', 'help_notify'),
                    Button.inline('💡 使用提示', 'help_tips'),
                ]
            ]
            return help_text, buttons
        
        @self.client.on(events.NewMessage(pattern='/adminhelp'))
        async def adminhelp_handler(event):
            """处理管理员帮助命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            help_text, buttons = _build_help_main()
            await event.respond(help_text, buttons=buttons, parse_mode='html')
            admin_info = await self._format_admin_log(event)
            logger.info(f"{admin_info} 查看了管理员帮助")
        
        @self.client.on(events.CallbackQuery(pattern=r'^help_'))
        async def help_callback_handler(event):
            """处理帮助分类按钮回调"""
            if not self.is_admin(event.sender_id):
                await event.answer('❌ 权限不足', alert=True)
                return
            
            try:
                data = event.data.decode('utf-8')
                category = data.replace('help_', '')
                
                # 根据分类返回不同的帮助内容
                help_texts = {
                    'stats': (
                        '📊 <b>统计查询功能</b>\n\n'
                        '<b>/tj</b> - 查看数据统计\n'
                        '• 显示查询次数、活跃用户、新增用户\n'
                        '• 支持查看日/周/月/年数据\n'
                        '• 使用内联按钮切换时间范围\n\n'
                        '<b>示例：</b>\n'
                        '<code>/tj</code> - 查看今日统计'
                    ),
                    'balance': (
                        '💰 <b>余额管理功能</b>\n\n'
                        '<b>/add &lt;用户ID&gt; &lt;金额&gt;</b>\n'
                        '• 增加指定用户的余额\n'
                        '• 示例: <code>/add 123456789 10</code>\n\n'
                        '<b>/deduct &lt;用户ID&gt; &lt;金额&gt;</b>\n'
                        '• 扣除指定用户的余额\n'
                        '• 会检查余额是否足够\n'
                        '• 示例: <code>/deduct 123456789 5</code>\n\n'
                        '<b>/set &lt;用户ID&gt; &lt;金额&gt;</b>\n'
                        '• 直接设置用户余额\n'
                        '• 示例: <code>/set 123456789 100</code>\n\n'
                        '<b>/checkbalance &lt;用户ID&gt;</b>\n'
                        '• 查询用户余额和签到信息\n'
                        '• 示例: <code>/checkbalance 123456789</code>'
                    ),
                    'config': (
                        '⚙️ <b>系统配置功能</b>\n\n'
                        '<b>签到配置：</b>\n'
                        '• <code>/setrange 最小值 最大值</code>\n'
                        '  设置签到奖励范围\n'
                        '  示例: /setrange 1 5\n\n'
                        '<b>消费配置：</b>\n'
                        '• <code>/setquerycost 金额</code>\n'
                        '  设置用户查询费用\n'
                        '  示例: /setquerycost 1\n'
                        '• <code>/settextsearchcost 金额</code>\n'
                        '  设置关键词查询费用\n'
                        '  示例: /settextsearchcost 1\n\n'
                        '<b>邀请配置：</b>\n'
                        '• <code>/setinvitereward 金额</code>\n'
                        '  设置邀请奖励\n'
                        '  示例: /setinvitereward 1\n\n'
                        '<b>充值配置：</b>\n'
                        '• <code>/setrechargetimeout 秒数</code>\n'
                        '  设置订单超时时间\n'
                        '  示例: /setrechargetimeout 1800\n'
                        '• <code>/setminrecharge 金额</code>\n'
                        '  设置最小充值金额\n'
                        '  示例: /setminrecharge 10\n'
                        '• <code>/setwallet 地址</code>\n'
                        '  设置充值钱包地址\n'
                        '  示例: /setwallet TXXXxxx...\n\n'
                        '<b>汇率配置：</b>\n'
                        '• <code>/setrate 货币 汇率</code>\n'
                        '  设置USDT/TRX汇率\n'
                        '  示例: /setrate USDT 7.2\n'
                        '• <code>/rates</code> - 查看当前汇率\n'
                        '• <code>/toggleapi</code> - 切换API开关\n\n'
                        '💡 所有配置立即生效'
                    ),
                    'hidden': (
                        '🔒 <b>隐藏用户管理</b>\n\n'
                        '<b>/hide &lt;用户名/ID&gt; [原因]</b>\n'
                        '• 隐藏指定用户的数据\n'
                        '• 用户查询时显示"已隐藏"\n'
                        '• 示例: <code>/hide durov 违规用户</code>\n'
                        '• 示例: <code>/hide 123456789</code>\n\n'
                        '<b>/unhide &lt;用户名/ID&gt;</b>\n'
                        '• 取消隐藏用户数据\n'
                        '• 示例: <code>/unhide durov</code>\n\n'
                        '<b>/hiddenlist</b>\n'
                        '• 查看所有已隐藏的用户列表\n\n'
                        '⚠️ <b>重要提示：</b>\n'
                        '建议同时隐藏用户名和ID\n'
                        '才能完全阻止查询！'
                    ),
                    'vip': (
                        '💎 <b>VIP管理功能</b>\n\n'
                        '<b>VIP价格配置：</b>\n'
                        '• <code>/setvipprice 积分</code>\n'
                        '  设置VIP月价格\n'
                        '  示例: /setvipprice 200\n'
                        '• <code>/setvippriceusdt 金额</code>\n'
                        '  以USDT设置VIP月价，自动换算为积分\n'
                        '  示例: /setvippriceusdt 30\n'
                        '• <code>/setvippricetrx 金额</code>\n'
                        '  以TRX设置VIP月价，自动换算为积分\n'
                        '  示例: /setvippricetrx 400\n\n'
                        '<b>VIP查询配额：</b>\n'
                        '• <code>/setvipuserquery 次数</code>\n'
                        '  设置VIP每日用户查询次数\n'
                        '  示例: /setvipuserquery 50\n'
                        '• <code>/setviptextquery 次数</code>\n'
                        '  设置VIP每日关键词查询次数\n'
                        '  示例: /setviptextquery 50\n\n'
                        '💱 <b>汇率配置已统一</b>\n'
                        '• 请前往“⚙️ 系统配置功能 → 汇率配置”使用 <code>/setrate</code>、<code>/rates</code>、<code>/toggleapi</code>\n\n'
                        '💎 <b>VIP专属权益：</b>\n'
                        '• 每日免费用户查询\n'
                        '• 每日免费关键词查询\n'
                        '• 解锁关联用户数据查看\n'
                        '• 超出免费次数后仍可使用积分查询'
                    ),
                    'service': (
                        '👨‍💼 <b>客服管理功能</b>\n\n'
                        '<b>/setservice</b> - 设置客服用户名\n\n'
                        '<b>使用步骤：</b>\n'
                        '1. 发送命令 <code>/setservice</code>\n'
                        '2. Bot回复提示消息\n'
                        '3. <b>引用回复</b>该消息并输入客服用户名\n'
                        '4. 设置成功后，用户将看到"联系客服"按钮\n\n'
                        '<b>支持格式：</b>\n'
                        '• 用户名: <code>username</code>\n'
                        '• @用户名: <code>@username</code>\n'
                        '• Telegram链接: <code>t.me/username</code>\n'
                        '• 完整链接: <code>https://t.me/username</code>\n\n'
                        '<b>/clearservice</b> - 清除客服设置\n'
                        '• 清除后用户将不再看到"联系客服"按钮\n\n'
                        '💡 用户点击"联系客服"按钮后会看到：\n'
                        '• 客服账号信息\n'
                        '• "开始对话"按钮（直达客服私聊）'
                    ),
                    'notify': (
                        '📢 <b>通知功能</b>\n\n'
                        '<b>/tz</b> - 发送系统通知\n\n'
                        '<b>使用步骤：</b>\n'
                        '1. 发送命令 <code>/tz</code>\n'
                        '2. Bot回复提示消息\n'
                        '3. <b>引用回复</b>该消息并输入通知内容\n'
                        '4. 确认后将发送给所有用户\n\n'
                        '<b>支持格式：</b>\n'
                        '• <code>&lt;b&gt;粗体&lt;/b&gt;</code> - <b>粗体</b>\n'
                        '• <code>&lt;i&gt;斜体&lt;/i&gt;</code> - <i>斜体</i>\n'
                        '• <code>&lt;code&gt;代码&lt;/code&gt;</code> - <code>代码</code>\n'
                        '• <code>&lt;a href="url"&gt;链接&lt;/a&gt;</code>\n\n'
                        '💡 通知会发送给所有使用过Bot的用户'
                    ),
                    'tips': (
                        '💡 <b>使用提示</b>\n\n'
                        '<b>💰 金额单位</b>\n'
                        '• 所有金额单位为 积分\n'
                        '• 签到奖励为整数\n\n'
                        '<b>📝 用户ID获取</b>\n'
                        '• 从运行日志中查看\n'
                        '• 日志格式: 用户 姓名 (@用户名, ID:数字)\n\n'
                        '<b>🔒 隐藏用户</b>\n'
                        '• 查询被隐藏用户时显示"已隐藏"\n'
                        '• 查询失败不扣费\n'
                        '• 建议同时隐藏用户名和ID\n\n'
                        '<b>⚙️ 配置修改</b>\n'
                        '• 签到范围修改后下次签到生效\n'
                        '• 查询费用修改后立即生效\n\n'
                        '<b>📊 数据统计</b>\n'
                        '• 日数据: 今日 00:00 起\n'
                        '• 周数据: 本周一 00:00 起\n'
                        '• 月数据: 本月1日 00:00 起\n'
                        '• 年数据: 今年1月1日 00:00 起'
                    )
                }
                
                help_text = help_texts.get(category, '❌ 未知分类')
                # 动态附加客服账号列表
                if category == 'service':
                    service_list = await self.db.get_service_accounts()
                    if service_list:
                        current = "\n\n<b>当前客服账号：</b>\n" + "\n".join([f"• <code>@{u}</code>" for u in service_list])
                    else:
                        current = "\n\n<b>当前客服账号：</b>无"
                    help_text = help_text + current
                
                # 创建返回按钮
                buttons = [
                    [Button.inline('🔙 返回主菜单', 'help_main')]
                ]
                
                await event.answer()
                await event.edit(help_text, buttons=buttons, parse_mode='html')
                
            except Exception as e:
                logger.error(f"帮助回调处理失败: {e}")
                await event.answer('❌ 处理失败', alert=True)
        
        @self.client.on(events.CallbackQuery(pattern=r'^help_main$'))
        async def help_main_callback_handler(event):
            """处理返回主菜单按钮"""
            if not self.is_admin(event.sender_id):
                await event.answer('❌ 权限不足', alert=True)
                return
            
            help_text, buttons = _build_help_main()
            await event.answer()
            await event.edit(help_text, buttons=buttons, parse_mode='html')
        
        @self.client.on(events.NewMessage(pattern='/tj'))
        async def stats_handler(event):
            """处理统计命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                # 默认分类: 查询数据，默认周期：今日
                category = 'query'
                period = 'day'
                stats = await self.db.get_query_stats(period)
                message = self._format_stats(stats)
                
                # 分类与周期按钮
                def build_buttons(cur_category: str, cur_period: str):
                    cat_names = {'query': '查询数据', 'user': '用户数据', 'recharge': '充值数据'}
                    cats_row = []
                    for c, name in cat_names.items():
                        text = f"✅ {name}" if c == cur_category else name
                        cats_row.append(Button.inline(text, f'stats_{c}_{cur_period}'))
                    
                    period_names = [('day','今日'), ('yesterday','昨日'), ('week','本周'), ('month','本月'), ('year','今年')]
                    p_row1 = []
                    p_row2 = []
                    for key, name in period_names:
                        text = f"✅ {name}" if key == cur_period else name
                        btn = Button.inline(text, f'stats_{cur_category}_{key}')
                        (p_row1 if key in ['day','yesterday','week'] else p_row2).append(btn)
                    return [cats_row, p_row1, p_row2]
                
                buttons = build_buttons(category, period)
                await event.respond(self._format_stats(stats), buttons=buttons, parse_mode='html')
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 查询了统计数据")
                
            except Exception as e:
                logger.error(f"统计命令处理失败: {e}")
                await event.respond('❌ 获取统计数据失败')
        
        @self.client.on(events.CallbackQuery(pattern=r'^stats_'))
        async def stats_callback_handler(event):
            """处理统计数据按钮回调"""
            if not self.is_admin(event.sender_id):
                await event.answer('❌ 权限不足', alert=True)
                return
            
            try:
                # 解析: stats_<category>_<period>
                data = event.data.decode('utf-8')
                _, category, period = data.split('_', 2)
                
                # 拉取数据
                if category == 'query':
                    stats = await self.db.get_query_stats(period)
                    message = self._format_stats(stats)
                elif category == 'user':
                    # 使用机器人用户数据（按周期）
                    qstats = await self.db.get_query_stats(period)
                    total_users = await self.db.get_total_bot_users()
                    message = (
                        f"👥 <b>用户数据（{qstats['period']}）</b>\n\n"
                        f"活跃用户: <code>{qstats.get('active_users', 0)}</code>\n"
                        f"新增用户: <code>{qstats.get('new_users', 0)}</code>\n"
                        f"累计使用用户: <code>{total_users}</code>"
                    )
                elif category == 'recharge':
                    rstats = await self.db.get_recharge_stats(period)
                    message = (
                        f"💳 <b>充值数据（{rstats['period']}）</b>\n\n"
                        f"完成订单: <code>{rstats['completed_orders']}</code>（VIP: <code>{rstats['vip_orders']}</code>，积分: <code>{rstats['recharge_orders']}</code>）\n"
                        f"USDT 实付: <code>{rstats['usdt_amount']:.4f}</code>\n"
                        f"TRX 实付: <code>{rstats['trx_amount']:.4f}</code>\n"
                        f"积分发放: <code>{rstats['total_points']:.2f}</code>"
                    )
                else:
                    message = '❌ 未知分类'
                
                # 构建按钮
                def build_buttons(cur_category: str, cur_period: str):
                    cat_names = {'query': '查询数据', 'user': '用户数据', 'recharge': '充值数据'}
                    cats_row = []
                    for c, name in cat_names.items():
                        text = f"✅ {name}" if c == cur_category else name
                        cats_row.append(Button.inline(text, f'stats_{c}_{cur_period}'))
                    period_names = [('day','今日'), ('yesterday','昨日'), ('week','本周'), ('month','本月'), ('year','今年')]
                    p_row1 = []
                    p_row2 = []
                    for key, name in period_names:
                        text = f"✅ {name}" if key == cur_period else name
                        btn = Button.inline(text, f'stats_{cur_category}_{key}')
                        (p_row1 if key in ['day','yesterday','week'] else p_row2).append(btn)
                    return [cats_row, p_row1, p_row2]
                
                buttons = build_buttons(category, period)
                
                await event.answer()
                await event.edit(message, buttons=buttons, parse_mode='html')
                
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 切换到{category}-{period}统计")
                
            except Exception as e:
                logger.error(f"统计回调处理失败: {e}")
                await event.answer('❌ 处理失败', alert=True)
        
        @self.client.on(events.NewMessage(pattern=r'/add\s+(\d+)\s+([\d.]+)'))
        async def add_balance_handler(event):
            """处理增加余额命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/add\s+(\d+)\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /add 用户ID 金额\n例: /add 123456789 10')
                    return
                
                target_user_id = int(match.group(1))
                amount = float(match.group(2))
                
                if amount <= 0:
                    await event.respond('❌ 金额必须大于0')
                    return
                
                # 增加余额
                success = await self.db.change_balance(
                    target_user_id, amount, 'admin_add',
                    f'管理员增加 {amount} 积分',
                    event.sender_id
                )
                
                if success:
                    new_balance = await self.db.get_balance(target_user_id)
                    await event.respond(
                        f'✅ <b>余额增加成功</b>\n\n'
                        f'用户ID: <code>{target_user_id}</code>\n'
                        f'增加金额: <code>{amount:.2f} 积分</code>\n'
                        f'当前余额: <code>{new_balance:.2f} 积分</code>',
                        parse_mode='html'
                    )
                    admin_info = await self._format_admin_log(event)
                    logger.info(f"{admin_info} 为用户 {target_user_id} 增加了 {amount} 积分")
                else:
                    await event.respond('❌ 操作失败，请稍后重试')
                    
            except Exception as e:
                logger.error(f"增加余额失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/deduct\s+(\d+)\s+([\d.]+)'))
        async def deduct_balance_handler(event):
            """处理扣除余额命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/deduct\s+(\d+)\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /deduct 用户ID 金额\n例: /deduct 123456789 5')
                    return
                
                target_user_id = int(match.group(1))
                amount = float(match.group(2))
                
                if amount <= 0:
                    await event.respond('❌ 金额必须大于0')
                    return
                
                # 检查余额
                current_balance = await self.db.get_balance(target_user_id)
                if current_balance < amount:
                    await event.respond(
                        f'❌ <b>余额不足，无法扣除</b>\n\n'
                        f'用户ID: <code>{target_user_id}</code>\n'
                        f'当前余额: <code>{current_balance:.2f} 积分</code>\n'
                        f'尝试扣除: <code>{amount:.2f} 积分</code>',
                        parse_mode='html'
                    )
                    return
                
                # 扣除余额
                success = await self.db.change_balance(
                    target_user_id, -amount, 'admin_deduct',
                    f'管理员扣除 {amount} 积分',
                    event.sender_id
                )
                
                if success:
                    new_balance = await self.db.get_balance(target_user_id)
                    await event.respond(
                        f'✅ <b>余额扣除成功</b>\n\n'
                        f'用户ID: <code>{target_user_id}</code>\n'
                        f'扣除金额: <code>{amount:.2f} 积分</code>\n'
                        f'当前余额: <code>{new_balance:.2f} 积分</code>',
                        parse_mode='html'
                    )
                    admin_info = await self._format_admin_log(event)
                    logger.info(f"{admin_info} 为用户 {target_user_id} 扣除了 {amount} 积分")
                else:
                    await event.respond('❌ 操作失败，请稍后重试')
                    
            except Exception as e:
                logger.error(f"扣除余额失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/set\s+(\d+)\s+([\d.]+)'))
        async def set_balance_handler(event):
            """处理设置余额命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/set\s+(\d+)\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /set 用户ID 金额\n例: /set 123456789 100')
                    return
                
                target_user_id = int(match.group(1))
                amount = float(match.group(2))
                
                if amount < 0:
                    await event.respond('❌ 金额不能为负数')
                    return
                
                # 获取当前余额
                old_balance = await self.db.get_balance(target_user_id)
                
                # 设置余额
                success = await self.db.change_balance(
                    target_user_id, amount, 'admin_set',
                    f'管理员设置余额为 {amount} 积分',
                    event.sender_id
                )
                
                if success:
                    await event.respond(
                        f'✅ <b>余额设置成功</b>\n\n'
                        f'用户ID: <code>{target_user_id}</code>\n'
                        f'原余额: <code>{old_balance:.2f} 积分</code>\n'
                        f'新余额: <code>{amount:.2f} 积分</code>',
                        parse_mode='html'
                    )
                    admin_info = await self._format_admin_log(event)
                    logger.info(f"{admin_info} 将用户 {target_user_id} 的余额设置为 {amount} 积分")
                else:
                    await event.respond('❌ 操作失败，请稍后重试')
                    
            except Exception as e:
                logger.error(f"设置余额失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/checkbalance\s+(\d+)'))
        async def check_balance_handler(event):
            """处理查询余额命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/checkbalance\s+(\d+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /checkbalance 用户ID\n例: /checkbalance 123456789')
                    return
                
                target_user_id = int(match.group(1))
                
                # 获取余额和签到信息
                balance = await self.db.get_balance(target_user_id)
                checkin_info = await self.db.get_checkin_info(target_user_id)
                
                await event.respond(
                    f'💰 <b>用户余额信息</b>\n\n'
                    f'用户ID: <code>{target_user_id}</code>\n'
                    f'当前余额: <code>{balance:.2f} 积分</code>\n\n'
                    f'📊 <b>统计信息</b>\n'
                    f'累计签到: <code>{checkin_info["total_days"]}</code> 天\n'
                    f'签到奖励: <code>{checkin_info["total_rewards"]:.2f} 积分</code>\n'
                    f'今日签到: <code>{"是" if checkin_info["today_checked"] else "否"}</code>',
                    parse_mode='html'
                )
                
            except Exception as e:
                logger.error(f"查询余额失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setrange\s+([\d.]+)\s+([\d.]+)'))
        async def setrange_handler(event):
            """处理设置签到范围命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setrange\s+([\d.]+)\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setrange 最小值 最大值\n例: /setrange 1 5')
                    return
                
                min_val = float(match.group(1))
                max_val = float(match.group(2))
                
                if min_val <= 0 or max_val <= 0:
                    await event.respond('❌ 金额必须大于0')
                    return
                
                if min_val > max_val:
                    await event.respond('❌ 最小值不能大于最大值')
                    return
                
                # 设置配置
                await self.db.set_config('checkin_min', str(min_val), '签到最小奖励')
                await self.db.set_config('checkin_max', str(max_val), '签到最大奖励')
                
                await event.respond(
                    f'✅ <b>签到奖励范围设置成功</b>\n\n'
                    f'最小值: <code>{min_val:.2f} 积分</code>\n'
                    f'最大值: <code>{max_val:.2f} 积分</code>\n\n'
                    f'💡 下次签到起生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置签到范围为 {min_val}-{max_val} 积分")
                
            except Exception as e:
                logger.error(f"设置签到范围失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setquerycost\s+([\d.]+)'))
        async def setquerycost_handler(event):
            """处理设置查询费用命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setquerycost\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setquerycost 金额\n例: /setquerycost 1')
                    return
                
                cost = float(match.group(1))
                
                if cost <= 0:
                    await event.respond('❌ 金额必须大于0')
                    return
                
                # 设置配置
                await self.db.set_config('query_cost', str(cost), '查询费用')
                
                await event.respond(
                    f'✅ <b>查询费用设置成功</b>\n\n'
                    f'新费用: <code>{cost:.2f} 积分</code>/次\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置查询费用为 {cost} 积分")
                
            except Exception as e:
                logger.error(f"设置查询费用失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/settextsearchcost\s+([\d.]+)'))
        async def settextsearchcost_handler(event):
            """处理设置关键词查询费用命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/settextsearchcost\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /settextsearchcost 金额\n例: /settextsearchcost 1')
                    return
                
                cost = float(match.group(1))
                
                if cost < 0:
                    await event.respond('❌ 金额不能为负数')
                    return
                
                # 设置配置
                await self.db.set_config('text_search_cost', str(cost), '关键词查询费用')
                
                cost_str = f'{int(cost)}' if cost == int(cost) else f'{cost:.2f}'
                await event.respond(
                    f'✅ <b>关键词查询费用设置成功</b>\n\n'
                    f'新费用: <code>{cost_str} 积分</code>/次\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置关键词查询费用为 {cost} 积分")
                
            except Exception as e:
                logger.error(f"设置关键词查询费用失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setvipprice\s+([\d.]+)'))
        async def setvipprice_handler(event):
            """处理设置VIP月价格命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setvipprice\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setvipprice 积分\n例: /setvipprice 200')
                    return
                
                price = float(match.group(1))
                
                if price < 0:
                    await event.respond('❌ 价格不能为负数')
                    return
                
                # 设置配置
                await self.db.set_config('vip_monthly_price', str(price), 'VIP月价格(积分)')
                
                price_str = f'{int(price)}' if price == int(price) else f'{price:.2f}'
                await event.respond(
                    f'✅ <b>VIP月价格设置成功</b>\n\n'
                    f'新价格: <code>{price_str} 积分</code>/月\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置VIP月价格为 {price} 积分")
                
            except Exception as e:
                logger.error(f"设置VIP月价格失败: {e}")
                await event.respond('❌ 命令处理失败')

        @self.client.on(events.NewMessage(pattern=r'/setvippriceusdt\s+([\d.]+)'))
        async def setvipprice_usdt_handler(event):
            """以USDT设置VIP价格（自动换算为积分）"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            try:
                import re
                match = re.match(r'/setvippriceusdt\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setvippriceusdt 金额\n例: /setvippriceusdt 30')
                    return
                usdt_amount = float(match.group(1))
                if usdt_amount < 0:
                    await event.respond('❌ 金额不能为负数')
                    return
                # 换算为积分
                points = await exchange_manager.usdt_to_points(usdt_amount)
                await self.db.set_config('vip_monthly_price', str(points), 'VIP月价格(积分)')
                await event.respond(
                    f'✅ <b>VIP月价格设置成功</b>\n\n'
                    f'新价格: <code>{points:.2f} 积分</code>/月\n'
                    f'（来源: <code>{usdt_amount}</code> USDT）',
                    parse_mode='html'
                )
            except Exception as e:
                logger.error(f"设置VIP月价格(USDT)失败: {e}")
                await event.respond('❌ 命令处理失败')

        @self.client.on(events.NewMessage(pattern=r'/setvippricetrx\s+([\d.]+)'))
        async def setvipprice_trx_handler(event):
            """以TRX设置VIP价格（自动换算为积分）"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            try:
                import re
                match = re.match(r'/setvippricetrx\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setvippricetrx 金额\n例: /setvippricetrx 400')
                    return
                trx_amount = float(match.group(1))
                if trx_amount < 0:
                    await event.respond('❌ 金额不能为负数')
                    return
                # 换算为积分
                points = await exchange_manager.trx_to_points(trx_amount)
                await self.db.set_config('vip_monthly_price', str(points), 'VIP月价格(积分)')
                await event.respond(
                    f'✅ <b>VIP月价格设置成功</b>\n\n'
                    f'新价格: <code>{points:.2f} 积分</code>/月\n'
                    f'（来源: <code>{trx_amount}</code> TRX）',
                    parse_mode='html'
                )
            except Exception as e:
                logger.error(f"设置VIP月价格(TRX)失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setvipuserquery\s+(\d+)'))
        async def setvipuserquery_handler(event):
            """处理设置VIP每日用户查询次数命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setvipuserquery\s+(\d+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setvipuserquery 次数\n例: /setvipuserquery 50')
                    return
                
                quota = int(match.group(1))
                
                if quota < 0:
                    await event.respond('❌ 次数不能为负数')
                    return
                
                # 设置配置
                await self.db.set_config('vip_daily_user_query', str(quota), 'VIP每日用户查询次数')
                
                await event.respond(
                    f'✅ <b>VIP每日用户查询次数设置成功</b>\n\n'
                    f'新配额: <code>{quota}</code> 次/天\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置VIP每日用户查询次数为 {quota}")
                
            except Exception as e:
                logger.error(f"设置VIP每日用户查询次数失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setviptextquery\s+(\d+)'))
        async def setviptextquery_handler(event):
            """处理设置VIP每日关键词查询次数命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setviptextquery\s+(\d+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setviptextquery 次数\n例: /setviptextquery 50')
                    return
                
                quota = int(match.group(1))
                
                if quota < 0:
                    await event.respond('❌ 次数不能为负数')
                    return
                
                # 设置配置
                await self.db.set_config('vip_daily_text_query', str(quota), 'VIP每日关键词查询次数')
                
                await event.respond(
                    f'✅ <b>VIP每日关键词查询次数设置成功</b>\n\n'
                    f'新配额: <code>{quota}</code> 次/天\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置VIP每日关键词查询次数为 {quota}")
                
            except Exception as e:
                logger.error(f"设置VIP每日关键词查询次数失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        # 已废弃：VIP专用汇率命令。请使用系统汇率命令 /setrate、/rates、/toggleapi
        
        @self.client.on(events.NewMessage(pattern=r'/setinvitereward\s+([\d.]+)'))
        async def setinvitereward_handler(event):
            """处理设置邀请奖励命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setinvitereward\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setinvitereward 金额\n例: /setinvitereward 1')
                    return
                
                reward = float(match.group(1))
                
                if reward <= 0:
                    await event.respond('❌ 奖励必须大于0')
                    return
                
                # 设置配置
                await self.db.set_config('invite_reward', str(reward), '邀请奖励')
                
                reward_str = f'{int(reward)}' if reward == int(reward) else f'{reward:.2f}'
                await event.respond(
                    f'✅ <b>邀请奖励设置成功</b>\n\n'
                    f'新奖励: <code>{reward_str} 积分</code>/人\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置邀请奖励为 {reward} 积分")
                
            except Exception as e:
                logger.error(f"设置邀请奖励失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setrate\s+(\w+)\s+([\d.]+)'))
        async def setrate_handler(event):
            """处理设置汇率命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setrate\s+(\w+)\s+([\d.]+)', event.text)
                if not match:
                    await event.respond(
                        '❌ 命令格式错误\n\n'
                        '正确格式: /setrate 货币 汇率\n\n'
                        '示例:\n'
                        '/setrate USDT 7.2  # 1 USDT = 7.2 积分\n'
                        '/setrate TRX 0.75  # 1 TRX = 0.75 积分'
                    )
                    return
                
                currency = match.group(1).upper()
                rate = float(match.group(2))
                
                if currency not in ['USDT', 'TRX']:
                    await event.respond('❌ 只支持设置 USDT 或 TRX 的汇率')
                    return
                
                if rate <= 0:
                    await event.respond('❌ 汇率必须大于0')
                    return
                
                # 设置固定汇率（内存）并持久化到数据库，确保/rates 及重启后一致
                exchange_manager.set_fixed_rate(currency, rate)
                # 持久化固定汇率
                if currency == 'USDT':
                    await self.db.set_config('fixed_rate_usdt_points', str(rate), '固定汇率: 1 USDT = ? 积分')
                else:
                    await self.db.set_config('fixed_rate_trx_points', str(rate), '固定汇率: 1 TRX = ? 积分')
                # 清理缓存
                exchange_manager.clear_cache()
                
                await event.respond(
                    f'✅ <b>汇率设置成功</b>\n\n'
                    f'货币: <code>{currency}</code>\n'
                    f'汇率: <code>1 {currency} = {rate:.4f} 积分</code>\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置{currency}汇率为 1:{rate}")
                
            except Exception as e:
                logger.error(f"设置汇率失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'^/rates$'))
        async def rates_handler(event):
            """查看当前汇率"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                rate_info = await exchange_manager.get_rate_info()
                
                usdt_rate = rate_info['usdt_to_points']
                trx_rate = rate_info['trx_to_points']
                using_api = rate_info['using_api']
                
                await event.respond(
                    f'💱 <b>当前汇率信息</b>\n\n'
                    f'<b>充值汇率：</b>\n'
                    f'• 1 USDT = <code>{usdt_rate:.4f}</code> 积分\n'
                    f'• 1 TRX = <code>{trx_rate:.4f}</code> 积分\n\n'
                    f'<b>兑换汇率：</b>\n'
                    f'• 1 积分 = <code>{1/usdt_rate:.4f}</code> USDT\n'
                    f'• 1 积分 = <code>{1/trx_rate:.4f}</code> TRX\n\n'
                    f'数据源: <code>{"Binance API" if using_api else "固定汇率"}</code>\n'
                    f'缓存: <code>{rate_info["cache_duration"]}秒</code>',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 查看了汇率信息")
                
            except Exception as e:
                logger.error(f"查看汇率失败: {e}")
                await event.respond('❌ 获取汇率信息失败')
        
        @self.client.on(events.NewMessage(pattern=r'^/toggleapi$'))
        async def toggleapi_handler(event):
            """切换API开关"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                # 切换状态
                new_state = not exchange_manager.use_api
                exchange_manager.enable_api(new_state)
                exchange_manager.clear_cache()
                # 持久化保存
                await self.db.set_config('exchange_use_api', '1' if new_state else '0', '汇率API开关')
                
                await event.respond(
                    f'✅ <b>API状态已切换</b>\n\n'
                    f'当前状态: <code>{"启用" if new_state else "禁用"}</code>\n\n'
                    f'{"📡 将从Binance获取实时汇率" if new_state else "📋 将使用固定汇率"}',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} {'启用' if new_state else '禁用'}了汇率API")
                
            except Exception as e:
                logger.error(f"切换API状态失败: {e}")
                await event.respond('❌ 操作失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setrechargetimeout\s+([\d]+)'))
        async def set_recharge_timeout_handler(event):
            """设置充值订单超时时间"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setrechargetimeout\s+([\d]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setrechargetimeout 秒数\n例: /setrechargetimeout 1800')
                    return
                
                timeout_seconds = int(match.group(1))
                
                if timeout_seconds < 300:
                    await event.respond('❌ 超时时间不能少于300秒（5分钟）')
                    return
                
                if timeout_seconds > 86400:
                    await event.respond('❌ 超时时间不能超过86400秒（24小时）')
                    return
                
                # 设置配置
                await self.db.set_config('recharge_timeout', str(timeout_seconds), '充值订单超时时间(秒)')
                
                timeout_minutes = timeout_seconds // 60
                await event.respond(
                    f'✅ <b>充值订单超时时间设置成功</b>\n\n'
                    f'新超时时间: <code>{timeout_seconds}</code> 秒 (<code>{timeout_minutes}</code> 分钟)\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置充值订单超时时间为 {timeout_seconds}秒")
                
            except Exception as e:
                logger.error(f"设置充值超时时间失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setminrecharge\s+([\d.]+)'))
        async def set_min_recharge_handler(event):
            """设置最小充值金额"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setminrecharge\s+([\d.]+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setminrecharge 金额\n例: /setminrecharge 10')
                    return
                
                min_amount = float(match.group(1))
                
                if min_amount <= 0:
                    await event.respond('❌ 最小金额必须大于0')
                    return
                
                if min_amount > 10000:
                    await event.respond('❌ 最小金额不能超过10000')
                    return
                
                # 设置配置
                await self.db.set_config('recharge_min_amount', str(min_amount), '最小充值金额')
                
                await event.respond(
                    f'✅ <b>最小充值金额设置成功</b>\n\n'
                    f'新最小金额: <code>{min_amount}</code>\n\n'
                    f'💡 立即生效',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置最小充值金额为 {min_amount}")
                
            except Exception as e:
                logger.error(f"设置最小充值金额失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'/setwallet\s+(\S+)'))
        async def set_wallet_handler(event):
            """设置充值钱包地址"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'/setwallet\s+(\S+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /setwallet 地址\n例: /setwallet TXXXxxx...')
                    return
                
                wallet_address = match.group(1).strip()
                
                # 简单验证TRON地址格式（以T开头，长度34）
                if not wallet_address.startswith('T') or len(wallet_address) != 34:
                    await event.respond('❌ 钱包地址格式错误\n\nTRON地址应以T开头，长度为34位')
                    return
                
                # 设置配置
                await self.db.set_config('recharge_wallet', wallet_address, '充值钱包地址')
                
                # 显示部分地址（隐藏中间部分）
                short_address = f"{wallet_address[:8]}...{wallet_address[-8:]}"
                
                await event.respond(
                    f'✅ <b>充值钱包地址设置成功</b>\n\n'
                    f'新钱包地址: <code>{wallet_address}</code>\n'
                    f'简写: <code>{short_address}</code>\n\n'
                    f'⚠️ <b>注意：需要重启Bot才能生效</b>',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 设置充值钱包地址为 {short_address}")
                
            except Exception as e:
                logger.error(f"设置充值钱包地址失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'^/hide\s+(\S+)'))
        async def hide_user_handler(event):
            """处理隐藏用户命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                # 匹配: /hide username [原因]
                match = re.match(r'^/hide\s+(\S+)(?:\s+(.+))?$', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /hide 用户名/ID [原因]\n例: /hide durov 违规用户')
                    return
                
                user_identifier = match.group(1)
                reason = match.group(2) or '无'
                
                # 隐藏用户
                success = await self.db.hide_user(user_identifier, event.sender_id, reason)
                
                if success:
                    # 判断是用户名还是ID
                    is_numeric = user_identifier.isdigit()
                    tip = ''
                    if is_numeric:
                        tip = '\n\n⚠️ <b>重要提示</b>\n您隐藏的是用户ID。建议同时隐藏该用户的用户名（如果有），以完全阻止查询：\n<code>/hide 用户名 相同原因</code>'
                    else:
                        tip = '\n\n💡 <b>提示</b>\n如果该用户有数字ID，建议同时隐藏其ID：\n<code>/hide 用户ID 相同原因</code>'
                    
                    await event.respond(
                        f'✅ <b>用户已隐藏</b>\n\n'
                        f'用户: <code>{user_identifier}</code>\n'
                        f'原因: <code>{reason}</code>\n\n'
                        f'🔒 该标识将无法被查询{tip}',
                        parse_mode='html'
                    )
                    admin_info = await self._format_admin_log(event)
                    logger.info(f"{admin_info} 隐藏了用户 {user_identifier}，原因: {reason}")
                else:
                    await event.respond('❌ 操作失败，请稍后重试')
                    
            except Exception as e:
                logger.error(f"隐藏用户失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern=r'^/unhide\s+(\S+)'))
        async def unhide_user_handler(event):
            """处理取消隐藏用户命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                import re
                match = re.match(r'^/unhide\s+(\S+)', event.text)
                if not match:
                    await event.respond('❌ 命令格式错误\n\n正确格式: /unhide 用户名/ID\n例: /unhide durov')
                    return
                
                user_identifier = match.group(1)
                
                # 检查是否已隐藏
                is_hidden = await self.db.is_user_hidden(user_identifier)
                if not is_hidden:
                    await event.respond(
                        f'⚠️ 用户 <code>{user_identifier}</code> 未被隐藏',
                        parse_mode='html'
                    )
                    return
                
                # 取消隐藏
                success = await self.db.unhide_user(user_identifier)
                
                if success:
                    await event.respond(
                        f'✅ <b>用户已取消隐藏</b>\n\n'
                        f'用户: <code>{user_identifier}</code>\n\n'
                        f'💡 该用户数据现在可以被正常查询',
                        parse_mode='html'
                    )
                    admin_info = await self._format_admin_log(event)
                    logger.info(f"{admin_info} 取消隐藏了用户 {user_identifier}")
                else:
                    await event.respond('❌ 操作失败，请稍后重试')
                    
            except Exception as e:
                logger.error(f"取消隐藏用户失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage(pattern='/hiddenlist'))
        async def hidden_list_handler(event):
            """处理查看隐藏用户列表命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                hidden_users = await self.db.get_hidden_users_list()
                
                if not hidden_users:
                    await event.respond('📋 当前没有隐藏的用户')
                    return
                
                # 构建列表消息
                message = f'🔒 <b>隐藏用户列表</b>\n\n共 {len(hidden_users)} 个用户\n\n'
                
                for idx, user in enumerate(hidden_users, 1):
                    user_id = user['user_identifier']
                    reason = user['reason']
                    hidden_at = user['hidden_at'][:10] if user['hidden_at'] else '未知'
                    
                    message += f'{idx}. <code>{user_id}</code>\n'
                    message += f'   原因: {reason}\n'
                    message += f'   时间: {hidden_at}\n\n'
                
                message += '💡 使用 /unhide 用户名 取消隐藏'
                
                await event.respond(message, parse_mode='html')
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 查看了隐藏用户列表")
                
            except Exception as e:
                logger.error(f"查看隐藏用户列表失败: {e}")
                await event.respond('❌ 获取列表失败')
        
        @self.client.on(events.NewMessage(pattern='/tz'))
        async def notify_handler(event):
            """处理通知命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                # 发送提示消息
                sent_msg = await event.respond(
                    '📢 <b>发送通知</b>\n\n'
                    '请引用回复此消息，并输入要发送的通知内容。\n\n'
                    '支持 HTML 格式，例如：\n'
                    '<code>&lt;b&gt;粗体&lt;/b&gt;</code>\n'
                    '<code>&lt;i&gt;斜体&lt;/i&gt;</code>\n'
                    '<code>&lt;code&gt;代码&lt;/code&gt;</code>\n'
                    '<code>&lt;a href="url"&gt;链接&lt;/a&gt;</code>',
                    parse_mode='html'
                )
                
                # 记录消息ID，等待回复
                self.pending_notifications.add(sent_msg.id)
                
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 准备发送通知")
                
            except Exception as e:
                logger.error(f"通知命令处理失败: {e}")
                await event.respond('❌ 命令处理失败')
        
        @self.client.on(events.NewMessage())
        async def notify_reply_handler(event):
            """处理通知内容回复"""
            # 检查是否为管理员
            if not self.is_admin(event.sender_id):
                return
            
            # 检查是否为回复消息
            if not event.is_reply:
                return
            
            try:
                # 获取被回复的消息
                reply_to_msg = await event.get_reply_message()
                
                # 检查是否回复了待处理的通知消息
                if reply_to_msg.id not in self.pending_notifications:
                    return
                
                # 移除待处理标记
                self.pending_notifications.discard(reply_to_msg.id)
                
                # 获取通知内容
                notification_content = event.text
                
                if not notification_content or notification_content.startswith('/'):
                    await event.respond('❌ 通知内容不能为空或命令')
                    return
                
                # 生成通知ID
                self.notification_counter += 1
                notify_id = self.notification_counter
                
                # 确认发送
                confirm_buttons = [
                    [
                        Button.inline('✅ 确认发送', f'notify_send_{notify_id}'),
                        Button.inline('❌ 取消', 'notify_cancel')
                    ]
                ]
                
                # 缓存通知内容
                cache_key = f"notify_{notify_id}"
                self.bot.query_cache[cache_key] = notification_content
                
                await event.respond(
                    f'📢 <b>通知预览</b>\n\n'
                    f'{notification_content}\n\n'
                    f'━━━━━━━━━━━━━━━━━━\n'
                    f'确认要发送此通知吗？',
                    buttons=confirm_buttons,
                    parse_mode='html'
                )
                
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 准备确认通知")
                
            except Exception as e:
                logger.error(f"通知回复处理失败: {e}")
        
        @self.client.on(events.CallbackQuery(pattern=r'^notify_send_'))
        async def confirm_notify_handler(event):
            """处理确认发送通知"""
            if not self.is_admin(event.sender_id):
                await event.answer('❌ 权限不足', alert=True)
                return
            
            try:
                # 解析通知ID
                data = event.data.decode('utf-8')
                notify_id = int(data.replace('notify_send_', ''))
                
                # 获取缓存的通知内容
                cache_key = f"notify_{notify_id}"
                notification_content = self.bot.query_cache.get(cache_key)
                
                if not notification_content:
                    await event.answer('❌ 通知内容已过期', alert=True)
                    return
                
                # 获取所有使用过Bot的用户
                cursor = await self.db.db.execute("""
                    SELECT DISTINCT querier_user_id FROM query_logs
                """)
                user_ids = [row[0] for row in await cursor.fetchall()]
                await cursor.close()
                
                if not user_ids:
                    await event.answer('❌ 没有找到用户', alert=True)
                    return
                
                # 响应回调
                await event.answer('开始发送通知...')
                await event.edit('📤 正在发送通知，请稍候...')
                
                # 发送通知
                success_count = 0
                fail_count = 0
                
                for user_id in user_ids:
                    try:
                        await self.client.send_message(
                            user_id,
                            f'📢 <b>系统通知</b>\n\n{notification_content}',
                            parse_mode='html'
                        )
                        success_count += 1
                    except Exception as e:
                        logger.debug(f"发送通知给用户 {user_id} 失败: {e}")
                        fail_count += 1
                
                # 清理缓存
                del self.bot.query_cache[cache_key]
                
                # 报告结果
                result_msg = (
                    f'✅ <b>通知发送完成</b>\n\n'
                    f'成功: {success_count} 人\n'
                    f'失败: {fail_count} 人\n'
                    f'总计: {len(user_ids)} 人'
                )
                
                await event.edit(result_msg, buttons=None, parse_mode='html')
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 发送了通知 (成功:{success_count}, 失败:{fail_count})")
                
            except Exception as e:
                logger.error(f"确认通知处理失败: {e}")
                await event.answer('❌ 发送失败', alert=True)
        
        @self.client.on(events.CallbackQuery(pattern=r'^notify_cancel$'))
        async def cancel_notify_handler(event):
            """处理取消通知"""
            if not self.is_admin(event.sender_id):
                await event.answer('❌ 权限不足', alert=True)
                return
            
            await event.answer('已取消')
            await event.edit('❌ 已取消发送通知', buttons=None)
            admin_info = await self._format_admin_log(event)
            logger.info(f"{admin_info} 取消了通知")
        
        @self.client.on(events.NewMessage(pattern=r'^/setservice$'))
        async def set_service_handler(event):
            """设置客服用户名命令"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            # 获取当前客服列表
            svc_list = await self.db.get_service_accounts()
            if svc_list:
                current_text = '\n当前客服：\n' + "\n".join([f"• <code>@{u}</code>" for u in svc_list])
            else:
                current_text = '\n当前未设置客服'
            
            prompt_msg = await event.respond(
                f'👨‍💼 <b>设置客服用户名</b>\n{current_text}\n\n'
                f'请回复此消息并提供客服用户名（支持多个，换行/逗号分隔）\n\n'
                f'<b>支持的格式：</b>\n'
                f'• 用户名: <code>username</code>\n'
                f'• @用户名: <code>@username</code>\n'
                f'• Telegram链接: <code>t.me/username</code>\n'
                f'• 完整链接: <code>https://t.me/username</code>\n\n'
                f'💡 回复此消息来设置，或发送 <code>/clearservice</code> 清除所有客服设置',
                parse_mode='html'
            )
            
            # 记录等待回复的消息ID
            self.pending_service_set.add(prompt_msg.id)
            admin_info = await self._format_admin_log(event)
            logger.info(f"{admin_info} 发起了设置客服")
        
        @self.client.on(events.NewMessage(pattern=r'^/clearservice$'))
        async def clear_service_handler(event):
            """清除客服设置"""
            if not self.is_admin(event.sender_id):
                await event.respond('❌ 此命令仅限管理员使用')
                return
            
            try:
                svc_list = await self.db.get_service_accounts()
                if not svc_list:
                    await event.respond('ℹ️ 当前未设置客服，无需清除')
                    return
                # 清除所有
                cleared = await self.db.clear_service_accounts()
                await event.respond(
                    f'✅ <b>客服设置已清除</b>\n\n'
                    f'清除数量: <code>{cleared}</code>\n\n'
                    f'💡 用户将不再看到"联系客服"按钮',
                    parse_mode='html'
                )
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 清除了客服设置")
                
            except Exception as e:
                logger.error(f"清除客服设置失败: {e}")
                await event.respond('❌ 清除失败')
        
        @self.client.on(events.NewMessage())
        async def service_reply_handler(event):
            """处理客服设置的回复"""
            if not self.is_admin(event.sender_id):
                return
            
            # 检查是否是回复消息
            if not event.is_reply:
                return
            
            # 获取回复的消息
            reply_msg = await event.get_reply_message()
            if not reply_msg or reply_msg.id not in self.pending_service_set:
                return
            
            try:
                # 支持批量解析多个用户名
                import re
                raw = event.text.strip()
                # 按换行/逗号/空白分隔
                parts = re.split(r'[\s,，、]+', raw)
                usernames = []
                for p in parts:
                    if not p:
                        continue
                    m = re.search(r'https?://t\.me/([A-Za-z0-9_]+)', p)
                    if m:
                        usernames.append(m.group(1))
                        continue
                    m = re.search(r'^(?:t\.me/)?@?([A-Za-z0-9_]+)$', p)
                    if m:
                        usernames.append(m.group(1))
                # 过滤非法长度
                usernames = [u for u in usernames if 3 <= len(u) <= 32]
                usernames = list(dict.fromkeys(usernames))  # 去重并保序
                if not usernames:
                    await event.respond('❌ 未解析到有效的用户名，请检查输入')
                    return
                # 保存到表
                result = await self.db.add_service_accounts(usernames, event.sender_id)
                # 移除等待状态
                self.pending_service_set.discard(reply_msg.id)
                # 反馈
                added_count = int(result.get('added', 0))
                skipped_count = int(result.get('skipped', 0))
                added_list = "\n".join([f"• <code>@{u}</code>" for u in usernames][:added_count])
                svc_list = await self.db.get_service_accounts()
                current = "\n".join([f"• <code>@{u}</code>" for u in svc_list]) if svc_list else '无'
                added_block = ("\n" + added_list) if added_count else ''
                text = (
                    '✅ <b>客服设置已更新</b>\n\n'
                    f'新增: <code>{added_count}</code>，已存在: <code>{skipped_count}</code>\n'
                    f'{added_block}\n\n'
                    f'<b>当前客服列表：</b>\n{current}'
                )
                await event.respond(text, parse_mode='html')
                admin_info = await self._format_admin_log(event)
                logger.info(f"{admin_info} 更新了客服账号: {usernames}")
            except Exception as e:
                logger.error(f"处理客服设置回复失败: {e}")
                await event.respond('❌ 设置失败，请重试')
    
    def _format_stats(self, stats: dict) -> str:
        """
        格式化统计信息
        
        Args:
            stats: 统计数据字典
        
        Returns:
            格式化的消息文本
        """
        period = stats.get('period', '未知')
        total_queries = stats.get('total_queries', 0)
        active_users = stats.get('active_users', 0)
        new_users = stats.get('new_users', 0)
        
        user_queries = stats.get('user_queries')
        text_queries = stats.get('text_queries')
        lines = [f'📊 <b>{period}数据统计</b>', '']
        if user_queries is not None and text_queries is not None:
            lines.append(f'🔎 用户查询: <code>{user_queries}</code>')
            lines.append(f'🔍 关键词查询: <code>{text_queries}</code>')
            lines.append(f'📈 合计查询: <code>{total_queries}</code>')
        else:
            lines.append(f'🔍 查询次数: <code>{total_queries}</code>')
        lines.append(f'👥 活跃用户: <code>{active_users}</code>')
        lines.append(f'🆕 新增用户: <code>{new_users}</code>')
        lines.append('')
        lines.append('━━━━━━━━━━━━━━━━━━')
        message = "\n".join(lines)
        
        return message

