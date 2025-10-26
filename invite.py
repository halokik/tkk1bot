"""
邀请模块 - 处理邀请相关功能
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import TelegramQueryBot

import config

logger = logging.getLogger(__name__)


class InviteModule:
    """邀请功能模块"""
    
    def __init__(self, bot_instance: 'TelegramQueryBot'):
        """
        初始化邀请模块
        
        Args:
            bot_instance: Bot实例
        """
        self.bot = bot_instance
        self.client = bot_instance.client
        self.db = bot_instance.db
        
        logger.info("邀请模块已加载")
    
    async def process_start_with_referral(self, event, referral_code: str) -> bool:
        """
        处理带邀请码的启动
        
        Args:
            event: 事件对象
            referral_code: 邀请码（邀请者的用户ID）
        
        Returns:
            是否成功处理邀请
        """
        try:
            # 验证邀请码是否为有效的数字ID
            if not referral_code.isdigit():
                logger.warning(f"无效的邀请码格式: {referral_code}")
                return False
            
            inviter_id = int(referral_code)
            invitee_id = event.sender_id
            
            # 检查被邀请者是否是老用户（已存在于数据库）
            is_existing = await self.db.is_existing_user(invitee_id)
            if is_existing:
                logger.info(f"用户 {invitee_id} 是老用户，邀请不生效")
                return False
            
            # 检查被邀请者是否已经被邀请过
            is_invited = await self.db.is_invited_user(invitee_id)
            if is_invited:
                logger.info(f"用户 {invitee_id} 已经被邀请过了")
                return False
            
            # 获取被邀请者信息
            sender = await event.get_sender()
            invitee_username = sender.username if hasattr(sender, 'username') else ''
            
            # 检查被邀请者是否设置了用户名
            if not invitee_username:
                await event.respond(
                    '⚠️ <b>邀请未生效</b>\n\n'
                    '您需要先设置 Telegram 用户名才能接受邀请。\n\n'
                    '<b>如何设置用户名：</b>\n'
                    '1. 打开 Telegram 设置\n'
                    '2. 点击"用户名"\n'
                    '3. 设置一个唯一的用户名\n'
                    '4. 重新点击邀请链接',
                    parse_mode='html'
                )
                logger.info(f"用户 {invitee_id} 未设置用户名，邀请未生效")
                return False
            
            # 记录邀请关系
            success, message = await self.db.record_invitation(
                inviter_id, invitee_id, invitee_username
            )
            
            if success:
                # 获取奖励金额
                invite_reward = float(await self.db.get_config('invite_reward', '1'))
                reward_str = f'{int(invite_reward)}' if invite_reward == int(invite_reward) else f'{invite_reward:.2f}'
                
                # 通知被邀请者
                await event.respond(
                    f'🎉 <b>欢迎通过邀请加入！</b>\n\n'
                    f'💰 您获得了 <code>{reward_str} 积分</code> 新人奖励！\n\n'
                    f'感谢使用我们的服务！',
                    parse_mode='html'
                )
                
                # 通知邀请者（使用之前获取的 reward_str）
                try:
                    await self.client.send_message(
                        inviter_id,
                        f'🎉 <b>邀请成功通知</b>\n\n'
                        f'您邀请的用户 @{invitee_username} 已成功加入！\n\n'
                        f'💰 您获得了 <code>{reward_str} 积分</code> 奖励\n'
                        f'💰 对方也获得了 <code>{reward_str} 积分</code> 新人奖励\n\n'
                        f'继续邀请更多朋友获得更多奖励吧！',
                        parse_mode='html'
                    )
                    logger.info(f"已通知邀请者 {inviter_id}")
                except Exception as e:
                    logger.error(f"通知邀请者失败: {e}")
                
                return True
            else:
                # 邀请失败（可能是已邀请过或自己邀请自己）
                if "已经通过邀请链接" in message:
                    # 静默处理，不显示错误消息
                    logger.info(f"用户 {invitee_id} 重复使用邀请链接")
                elif "不能使用自己" in message:
                    logger.info(f"用户 {invitee_id} 尝试使用自己的邀请链接")
                else:
                    await event.respond(f'⚠️ {message}', parse_mode='html')
                
                return False
                
        except Exception as e:
            logger.error(f"处理邀请失败: {e}")
            return False
    
    def get_invite_link(self, user_id: int) -> str:
        """
        生成用户的邀请链接
        
        Args:
            user_id: 用户ID
        
        Returns:
            邀请链接
        """
        bot_username = self.bot.bot_username
        return f"https://t.me/{bot_username}?start={user_id}"

