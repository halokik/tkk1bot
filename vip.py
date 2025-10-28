"""
VIP 模块 - 处理VIP购买、权益管理等功能
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from telethon import events, Button
from exchange import exchange_manager

logger = logging.getLogger(__name__)


class VIPModule:
    """VIP功能模块"""
    
    def __init__(self, client, db):
        """初始化VIP模块"""
        self.client = client
        self.db = db
        self.pending_vip_purchase = {}  # 存储VIP购买状态
        
    async def show_vip_purchase_menu(self, event, is_edit=True, selected_months=3):
        """显示VIP购买菜单（一页式）"""
        try:
            # 获取VIP价格配置
            vip_price = float(await self.db.get_config('vip_monthly_price', '200'))
            monthly_quota = int(await self.db.get_config('vip_monthly_query_limit', '3999'))
            
            # 计算选中月份的价格
            total_points = vip_price * selected_months
            total_usdt = await exchange_manager.points_to_usdt(total_points)
            total_trx = await exchange_manager.points_to_trx(total_points)
            
            text = (
                f"💎 <b>VIP会员开通</b>\n\n"
                f"• 每月 {monthly_quota} 次查询（免积分）\n"
                f"• 解锁关联用户数据查看功能\n"
                f"• 超出免费次数后仍可使用积分查询\n\n"
                f"<b>{total_usdt:.2f} USDT / {total_trx:.2f} TRX</b>\n"
                f"（一次支付，安全可靠）\n\n"
                f"👇 请选择购买时长："
            )
            
            # 月份选择按钮（带对钩标记）
            buttons = [
                [
                    Button.inline(f"{'☑️ ' if selected_months == 1 else '◻️ '}1 个月", b"vip_select_1"),
                    Button.inline(f"{'☑️ ' if selected_months == 3 else '◻️ '}3 个月", b"vip_select_3"),
                    Button.inline(f"{'☑️ ' if selected_months == 6 else '◻️ '}6 个月", b"vip_select_6")
                ],
                [
                    Button.inline(f"{'☑️ ' if selected_months == 12 else '◻️ '}12 个月", b"vip_select_12"),
                ],
            ]
            
            # 支付方式选择
            buttons.append([
                Button.inline("💎 USDT支付", f"vip_pay_{selected_months}_usdt"),
                Button.inline("💵 TRX支付", f"vip_pay_{selected_months}_trx")
            ])
            
            buttons.append([Button.inline("« 返回主菜单", b"cmd_back_to_start")])
            
            if is_edit:
                await event.edit(text, buttons=buttons, parse_mode='html')
            else:
                await event.respond(text, buttons=buttons, parse_mode='html')
                
        except Exception as e:
            logger.error(f"显示VIP购买菜单错误: {e}")
            await event.respond("❌ 系统错误，请稍后再试")
    
    async def show_vip_month_selector(self, event, current_months=1):
        """显示VIP月份选择器（可加减）"""
        try:
            # 获取VIP价格配置
            vip_price = float(await self.db.get_config('vip_monthly_price', '200'))
            
            # 限制范围 1-99
            current_months = max(1, min(99, current_months))
            
            total_points = vip_price * current_months
            total_usdt = await exchange_manager.points_to_usdt(total_points)
            total_trx = await exchange_manager.points_to_trx(total_points)
            
            # 获取用户当前VIP信息
            vip_info = await self.db.get_user_vip_info(event.sender_id)
            expire_text = ""
            if vip_info and vip_info['expire_time']:
                expire_dt = datetime.fromisoformat(vip_info['expire_time'])
                new_expire = expire_dt + timedelta(days=30 * current_months)
                expire_text = f"\n📅 <b>新到期时间：</b>{new_expire.strftime('%Y-%m-%d %H:%M')}"
            else:
                new_expire = datetime.now() + timedelta(days=30 * current_months)
                expire_text = f"\n📅 <b>到期时间：</b>{new_expire.strftime('%Y-%m-%d %H:%M')}"
            
            text = (
                f"💎 <b>VIP会员开通</b>\n\n"
                f"⏱ <b>购买时长：</b>{current_months} 个月\n"
                f"💵 <b>约合：</b>{total_usdt:.2f} USDT / {total_trx:.2f} TRX{expire_text}\n\n"
                f"👇 调整时长后选择支付方式："
            )
            
            buttons = []
            
            # 加减按钮行
            row = []
            if current_months > 1:
                row.append(Button.inline("-10", f"vip_adj_{current_months}_-10"))
                row.append(Button.inline("-1", f"vip_adj_{current_months}_-1"))
            row.append(Button.inline(f"🌟 {current_months} 月", b"vip_month_noop"))
            if current_months < 99:
                row.append(Button.inline("+1", f"vip_adj_{current_months}_+1"))
                row.append(Button.inline("+10", f"vip_adj_{current_months}_+10"))
            buttons.append(row)
            
            # 支付方式选择
            buttons.append([
                Button.inline("💎 USDT支付", f"vip_pay_{current_months}_usdt"),
                Button.inline("💵 TRX支付", f"vip_pay_{current_months}_trx")
            ])
            
            buttons.append([Button.inline("« 返回", b"vip_menu")])
            
            await event.edit(text, buttons=buttons, parse_mode='html')
            
        except Exception as e:
            logger.error(f"显示VIP月份选择器错误: {e}")
            await event.respond("❌ 系统错误，请稍后再试")
    
    async def create_vip_order(self, event, months: int, currency: str):
        """创建VIP购买订单"""
        try:
            user_id = event.sender_id
            
            # 获取价格配置
            vip_price = float(await self.db.get_config('vip_monthly_price', '200'))
            
            # 计算金额
            total_points = vip_price * months
            
            # 根据币种计算金额
            if currency.upper() == 'USDT':
                amount = await exchange_manager.points_to_usdt(total_points)
            else:  # TRX
                amount = await exchange_manager.points_to_trx(total_points)
            
            # 创建订单（复用充值订单表）
            order_id = await self.db.create_vip_order(
                user_id=user_id,
                months=months,
                currency=currency.upper(),
                amount=amount,
                points_value=total_points
            )
            
            if not order_id:
                await event.respond("❌ 创建订单失败，请稍后再试")
                return None
            
            return {
                'order_id': order_id,
                'months': months,
                'currency': currency.upper(),
                'amount': amount,
                'points_value': total_points
            }
            
        except Exception as e:
            logger.error(f"创建VIP订单错误: {e}")
            await event.respond("❌ 系统错误，请稍后再试")
            return None
    
    async def check_and_use_daily_quota(self, user_id: int, query_type: str) -> Dict[str, Any]:
        """
        检查并使用月度配额（保留方法名兼容性）
        
        Args:
            user_id: 用户ID
            query_type: 查询类型（已废弃，统一计数）
            
        Returns:
            {
                'is_vip': bool,
                'can_use_quota': bool,  # 是否可以使用免费配额
                'remaining': int,  # 剩余次数
                'total': int  # 总配额
            }
        """
        try:
            # 检查是否为VIP
            vip_info = await self.db.get_user_vip_info(user_id)
            
            if not vip_info or not vip_info['is_vip']:
                return {
                    'is_vip': False,
                    'can_use_quota': False,
                    'remaining': 0,
                    'total': 0
                }
            
            # 获取月度配额配置
            monthly_quota = int(await self.db.get_config('vip_monthly_query_limit', '3999'))
            
            # 获取本月使用情况
            usage = await self.db.get_monthly_query_usage(user_id)
            used = usage['used']
            
            if used < monthly_quota:
                # 还有配额，使用一次
                await self.db.increment_monthly_query_usage(user_id)
                return {
                    'is_vip': True,
                    'can_use_quota': True,
                    'remaining': monthly_quota - used - 1,
                    'total': monthly_quota
                }
            else:
                # 配额用完
                return {
                    'is_vip': True,
                    'can_use_quota': False,
                    'remaining': 0,
                    'total': monthly_quota
                }
                
        except Exception as e:
            logger.error(f"检查月度配额错误: {e}")
            return {
                'is_vip': False,
                'can_use_quota': False,
                'remaining': 0,
                'total': 0
            }
    
    async def get_vip_display_info(self, user_id: int) -> str:
        """获取VIP显示信息（用于个人中心）"""
        try:
            vip_info = await self.db.get_user_vip_info(user_id)
            
            if not vip_info or not vip_info['is_vip']:
                return "<b>用户类型：</b>普通用户"
            
            expire_dt = datetime.fromisoformat(vip_info['expire_time'])
            expire_str = expire_dt.strftime('%Y-%m-%d %H:%M')
            
            # 获取本月查询使用情况
            usage = await self.db.get_monthly_query_usage(user_id)
            monthly_quota = int(await self.db.get_config('vip_monthly_query_limit', '3999'))
            
            remaining = max(0, monthly_quota - usage['used'])
            
            return (
                f"💎 <b>用户类型：</b>VIP会员\n"
                f"📅 <b>到期时间：</b>{expire_str}\n"
                f"🎯 <b>本月免费查询：</b>{remaining}/{monthly_quota} 次"
            )
            
        except Exception as e:
            logger.error(f"获取VIP显示信息错误: {e}")
            return "<b>用户类型：</b>普通用户"
    
    async def handle_vip_callback(self, event):
        """处理VIP相关的回调"""
        data = event.data.decode('utf-8')
        
        try:
            if data == "vip_menu":
                # 显示VIP菜单（默认选择3个月）
                await self.show_vip_purchase_menu(event, selected_months=3)
                
            elif data.startswith("vip_select_"):
                # 选择月份（更新菜单显示）
                month_str = data.replace("vip_select_", "")
                months = int(month_str)
                await event.answer()
                await self.show_vip_purchase_menu(event, selected_months=months)
                
            elif data.startswith("vip_pay_"):
                # 选择支付方式，直接创建订单
                parts = data.replace("vip_pay_", "").split("_")
                months = int(parts[0])
                currency = parts[1]
                
                # 创建订单并跳转到支付流程
                await event.answer("正在创建订单...", alert=False)
                created = await self.create_vip_order(event, months, currency)
                if created and created.get('order_id'):
                    order = await self.db.get_order_by_id(created['order_id'])
                    if order:
                        await self._show_vip_order(event, order)
                else:
                    await event.answer("❌ 创建订单失败", alert=True)
                    
        except Exception as e:
            logger.error(f"处理VIP回调错误: {e}")
            await event.answer("❌ 操作失败", alert=True)
    
    async def _show_vip_order(self, event, order: Dict[str, Any]):
        """显示VIP订单信息"""
        try:
            from datetime import datetime
            
            currency = order['currency']
            actual_amount = order['actual_amount']
            wallet = order['wallet_address']
            vip_months = order['vip_months']
            expired_at = order['expired_at']
            
            # 计算剩余时间
            try:
                expire_time = datetime.fromisoformat(expired_at)
                remaining_seconds = (expire_time - datetime.now()).total_seconds()
                remaining_minutes = max(0, int(remaining_seconds // 60))
            except:
                remaining_minutes = 30  # 备用值
            
            buttons = [
                [Button.inline('❌ 取消订单', f"cancel_order_{order['order_id']}")]
            ]
            
            # 发送新消息而不是编辑
            await event.respond(
                f'⚠️ <b>您有未完成的订单</b>\n\n'
                f'💎 <b>VIP开通订单</b>\n\n'
                f'<b>订单号:</b> <code>{order["order_id"]}</code>\n'
                f'<b>开通时长:</b> {vip_months} 个月\n'
                f'<b>支付币种:</b> {currency}\n'
                f'<b>支付金额:</b> <code>{actual_amount}</code> {currency}\n\n'
                f'<b>收款地址:</b>\n<code>{wallet}</code>\n\n'
                f'⏰ <b>剩余时间:</b> {remaining_minutes} 分钟\n\n'
                f'💡 <b>请务必转账准确金额 {actual_amount}，否则无法自动到账！</b>\n'
                f'💎 <b>付款成功后将自动激活VIP权益</b>',
                buttons=buttons,
                parse_mode='html'
            )
            
        except Exception as e:
            logger.error(f"显示VIP订单失败: {e}")
            await event.respond("❌ 显示订单失败")

