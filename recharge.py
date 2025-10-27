"""
充值模块 - 处理TRON链（USDT/TRX）充值
基于区块扫描实现
"""
import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from telethon import Button
import config
from exchange import exchange_manager

logger = logging.getLogger(__name__)


class TronBlockScanner:
    """TRON区块扫描器"""
    
    def __init__(self, db, recharge_module=None):
        """
        初始化扫描器
        
        Args:
            db: 数据库实例
            recharge_module: 充值模块实例（用于回调通知）
        """
        self.db = db
        self.recharge_module = recharge_module
        self.api_url = config.TRON_API_URL
        self.api_key = config.TRON_API_KEY
        self.usdt_contract = config.USDT_CONTRACT
        self.wallet_address = config.RECHARGE_WALLET_ADDRESS
        
        # 扫描间隔（秒）
        self.scan_interval = 3
        
        # 是否正在运行
        self.is_running = False
        
        logger.info(f"TRON扫描器已初始化 - 网络: {config.TRON_NETWORK}, 钱包: {self.wallet_address}")
    
    async def _make_request(self, endpoint: str, params: Dict = None, json_data: Dict = None) -> Optional[Dict]:
        """发起HTTP请求"""
        try:
            url = f"{self.api_url}{endpoint}"
            headers = {}
            if self.api_key:
                headers['TRON-PRO-API-KEY'] = self.api_key
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if json_data:
                    async with session.post(url, json=json_data, headers=headers) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.warning(f"请求失败: {endpoint}, 状态码: {response.status}")
                else:
                    async with session.get(url, params=params, headers=headers) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.warning(f"请求失败: {endpoint}, 状态码: {response.status}")
        except asyncio.TimeoutError:
            logger.error(f"请求超时: {endpoint}")
        except Exception as e:
            logger.error(f"请求异常: {endpoint}, 错误: {e}")
        
        return None
    
    async def get_latest_block_number(self) -> Optional[int]:
        """获取最新区块号"""
        try:
            result = await self._make_request('/wallet/getnowblock')
            if result and 'block_header' in result:
                block_number = result['block_header']['raw_data']['number']
                return block_number
            return None
        except Exception as e:
            logger.error(f"获取最新区块号失败: {e}")
            return None
    
    async def get_block_by_number(self, block_number: int) -> Optional[Dict]:
        """根据区块号获取区块数据"""
        try:
            json_data = {'num': block_number}
            result = await self._make_request('/wallet/getblockbynum', json_data=json_data)
            return result
        except Exception as e:
            logger.error(f"获取区块 {block_number} 失败: {e}")
            return None
    
    def _hex_to_address(self, hex_address: str) -> str:
        """将十六进制地址转换为Base58地址"""
        try:
            # 移除0x前缀
            if hex_address.startswith('0x'):
                hex_address = hex_address[2:]
            
            # 添加41前缀（TRON主网地址前缀）
            if not hex_address.startswith('41'):
                hex_address = '41' + hex_address
            
            # 方法1: 使用base58库（推荐）
            try:
                from base58 import b58encode_check
                import binascii
                
                # 转换为字节
                address_bytes = binascii.unhexlify(hex_address)
                
                # Base58编码
                base58_address = b58encode_check(address_bytes).decode('utf-8')
                
                return base58_address
            except ImportError:
                # 方法2: 如果没有base58库，使用内置实现
                logger.warning("base58库未安装，使用内置实现")
                return self._hex_to_base58_builtin(hex_address)
                
        except Exception as e:
            logger.error(f"地址转换失败: {hex_address}, 错误: {e}")
            return hex_address
    
    def _hex_to_base58_builtin(self, hex_address: str) -> str:
        """使用内置库进行Base58转换（备用方案）"""
        try:
            import hashlib
            import binascii
            
            # Base58字符集
            BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
            
            # 十六进制转字节
            address_bytes = binascii.unhexlify(hex_address)
            
            # 计算校验和
            hash1 = hashlib.sha256(address_bytes).digest()
            hash2 = hashlib.sha256(hash1).digest()
            checksum = hash2[:4]
            
            # 添加校验和
            address_with_checksum = address_bytes + checksum
            
            # 转换为大整数
            num = int.from_bytes(address_with_checksum, 'big')
            
            # Base58编码
            encoded = ''
            while num > 0:
                num, remainder = divmod(num, 58)
                encoded = BASE58_ALPHABET[remainder] + encoded
            
            # 处理前导零
            for byte in address_with_checksum:
                if byte == 0:
                    encoded = '1' + encoded
                else:
                    break
            
            return encoded
            
        except Exception as e:
            logger.error(f"内置Base58转换失败: {e}")
            return hex_address
    
    def _parse_trx_value(self, amount_sun: int) -> float:
        """将SUN转换为TRX (1 TRX = 1,000,000 SUN)"""
        return amount_sun / 1_000_000
    
    def _parse_usdt_value(self, hex_value: str) -> float:
        """解析USDT金额 (USDT有6位小数)"""
        try:
            # 将十六进制转换为整数
            value_int = int(hex_value, 16)
            # USDT使用6位小数
            return value_int / 1_000_000
        except Exception as e:
            logger.error(f"解析USDT金额失败: {hex_value}, 错误: {e}")
            return 0
    
    async def _process_trx_transaction(self, tx: Dict) -> None:
        """处理TRX交易"""
        try:
            if 'raw_data' not in tx:
                return
            
            raw_data = tx['raw_data']
            if 'contract' not in raw_data:
                return
            
            for contract in raw_data['contract']:
                contract_type = contract['type']
                order = None  # 初始化order变量
                
                # 打印所有转账类型的合约
                if contract_type == 'TransferContract':
                    parameter = contract['parameter']['value']
                    to_address_hex = parameter.get('to_address', '')
                    from_address_hex = parameter.get('owner_address', '')
                    amount_sun = parameter.get('amount', 0)
                    
                    # logger.info(f"📝 [TRX交易原始数据]")
                    # logger.info(f"   From HEX: {from_address_hex}")
                    # logger.info(f"   To HEX: {to_address_hex}")
                    # logger.info(f"   Amount SUN: {amount_sun}")
                    
                    # 转换地址
                    to_address = self._hex_to_address(to_address_hex)
                    from_address = self._hex_to_address(from_address_hex)
                    
                    # logger.info(f"   From Base58: {from_address}")
                    # logger.info(f"   To Base58: {to_address}")
                    # logger.info(f"   我们的钱包: {self.wallet_address}")
                    # logger.info(f"   地址匹配: {to_address == self.wallet_address}")
                    
                    # 检查是否转账到我们的钱包
                    if to_address != self.wallet_address:
                        # logger.debug(f"   ❌ 地址不匹配，跳过")
                        continue
                    
                    # 转换金额
                    amount_trx = self._parse_trx_value(amount_sun)
                    
                    # 四舍五入到小数点后2位
                    amount_trx = round(amount_trx, 2)
                    
                    logger.info(f"💎 检测到TRX转账: {amount_trx} TRX → {to_address}")
                    
                    # 查找对应的订单
                    order = await self.db.find_order_by_amount(amount_trx, 'TRX')
                    
                    if not order:
                        logger.warning(f"⚠️ 未找到金额 {amount_trx} TRX 对应的订单")
                    else:
                        logger.info(f"✅ 找到订单: {order['order_id']}")
                
                if order:
                    # 获取交易哈希
                    tx_hash = tx.get('txID', '')
                    
                    # 计算应获得的积分（使用实际转账金额）
                    points = await exchange_manager.trx_to_points(amount_trx)
                    
                    # 完成订单
                    success = await self.db.complete_recharge_order(order['order_id'], tx_hash, points)
                    
                    if success:
                        logger.info(f"TRX充值成功: 订单{order['order_id']}, 金额{amount_trx}, 积分{points}")
                        
                        # 通知用户
                        if self.recharge_module:
                            await self.recharge_module.notify_recharge_success(
                                order['user_id'], order['order_id'], 'TRX',
                                amount_trx, points, tx_hash
                            )
                
        except Exception as e:
            logger.error(f"处理TRX交易失败: {e}")
    
    async def _process_usdt_transaction(self, tx: Dict) -> None:
        """处理USDT交易（TRC20代币）"""
        try:
            if 'raw_data' not in tx:
                return
            
            raw_data = tx['raw_data']
            if 'contract' not in raw_data:
                return
            
            for contract in raw_data['contract']:
                contract_type = contract['type']
                order = None  # 初始化order变量
                
                if contract_type != 'TriggerSmartContract':
                    continue
                
                parameter = contract['parameter']['value']
                contract_address_hex = parameter.get('contract_address', '')
                from_address_hex = parameter.get('owner_address', '')
                
                # logger.info(f"📝 [智能合约调用原始数据]")
                # logger.info(f"   From HEX: {from_address_hex}")
                # logger.info(f"   Contract HEX: {contract_address_hex}")
                
                # 转换合约地址
                contract_address = self._hex_to_address(contract_address_hex)
                from_address = self._hex_to_address(from_address_hex)
                
                # logger.info(f"   From Base58: {from_address}")
                # logger.info(f"   Contract Base58: {contract_address}")
                # logger.info(f"   USDT合约: {self.usdt_contract}")
                # logger.info(f"   合约匹配: {contract_address == self.usdt_contract}")
                
                # 检查是否是USDT合约
                if contract_address != self.usdt_contract:
                    # logger.debug(f"   ❌ 非USDT合约，跳过")
                    continue
                
                # 解析transfer方法调用
                data = parameter.get('data', '')
                # logger.info(f"   Data长度: {len(data)}")
                # logger.info(f"   Data: {data[:40]}..." if len(data) > 40 else f"   Data: {data}")
                
                if len(data) < 136:  # transfer方法最少需要136字符
                    # logger.warning(f"   ⚠️ Data长度不足136，跳过")
                    continue
                
                # 提取接收地址和金额
                # transfer(address,uint256)的data格式:
                # 0-8: 方法签名
                # 8-72: 接收地址（前24个0 + 20字节地址）
                # 72-136: 金额
                
                method_sig = data[0:8]
                to_address_hex = data[32:72]  # 提取地址部分
                amount_hex = data[72:136]  # 提取金额部分
                
                # logger.info(f"   方法签名: {method_sig}")
                # logger.info(f"   To地址HEX: {to_address_hex}")
                # logger.info(f"   金额HEX: {amount_hex}")
                
                # 转换地址
                to_address = self._hex_to_address(to_address_hex)
                
                # logger.info(f"   To Base58: {to_address}")
                # logger.info(f"   我们的钱包: {self.wallet_address}")
                # logger.info(f"   地址匹配: {to_address == self.wallet_address}")
                
                # 检查是否转账到我们的钱包
                if to_address != self.wallet_address:
                    # logger.debug(f"   ❌ 地址不匹配，跳过")
                    continue
                
                # 解析金额
                amount_usdt = self._parse_usdt_value(amount_hex)
                
                # 四舍五入到小数点后2位
                amount_usdt = round(amount_usdt, 2)
                
                logger.info(f"💵 检测到USDT转账: {amount_usdt} USDT → {to_address}")
                
                # 查找对应的订单
                order = await self.db.find_order_by_amount(amount_usdt, 'USDT')
                
                if not order:
                    logger.warning(f"⚠️ 未找到金额 {amount_usdt} USDT 对应的订单")
                else:
                    logger.info(f"✅ 找到订单: {order['order_id']}")
                
                if order:
                    # 获取交易哈希
                    tx_hash = tx.get('txID', '')
                    
                    # 计算应获得的积分（使用实际转账金额）
                    points = await exchange_manager.usdt_to_points(amount_usdt)
                    
                    # 完成订单
                    success = await self.db.complete_recharge_order(order['order_id'], tx_hash, points)
                    
                    if success:
                        logger.info(f"USDT充值成功: 订单{order['order_id']}, 金额{amount_usdt}, 积分{points}")
                        
                        # 通知用户
                        if self.recharge_module:
                            await self.recharge_module.notify_recharge_success(
                                order['user_id'], order['order_id'], 'USDT',
                                amount_usdt, points, tx_hash
                            )
                
        except Exception as e:
            logger.error(f"处理USDT交易失败: {e}")
    
    async def scan_block(self, block_number: int) -> None:
        """扫描单个区块"""
        try:
            block_data = await self.get_block_by_number(block_number)
            
            if not block_data or 'transactions' not in block_data:
                logger.debug(f"区块 {block_number} 无数据或无交易")
                return
            
            transactions = block_data['transactions']
            
            if not transactions:
                # logger.debug(f"区块 {block_number} 交易列表为空")
                return
            
            # logger.info(f"🔍 扫描区块 {block_number}, 交易数: {len(transactions)}")
            
            # 处理每笔交易
            for tx in transactions:
                # 同时处理TRX和USDT
                await self._process_trx_transaction(tx)
                await self._process_usdt_transaction(tx)
            
            # 保存扫描记录
            await self.db.save_block_scan('TRX', block_number)
            await self.db.save_block_scan('USDT', block_number)
            
        except Exception as e:
            logger.error(f"扫描区块 {block_number} 失败: {e}")
    
    async def start_scanning(self) -> None:
        """开始扫描区块"""
        if self.is_running:
            logger.warning("扫描器已在运行中")
            return
        
        self.is_running = True
        logger.info("🚀 开始扫描TRON区块")
        logger.info(f"📡 网络: {config.TRON_NETWORK}")
        logger.info(f"💼 钱包地址: {self.wallet_address}")
        logger.info(f"🔄 扫描间隔: {self.scan_interval}秒")
        
        while self.is_running:
            try:
                # 获取最新区块号
                latest_block = await self.get_latest_block_number()
                
                if not latest_block:
                    logger.warning("无法获取最新区块号，等待重试...")
                    await asyncio.sleep(self.scan_interval)
                    continue
                
                # 获取上次扫描的区块号
                last_scanned = await self.db.get_last_scanned_block('TRX')
                
                if not last_scanned:
                    # 首次扫描，从当前区块开始
                    last_scanned = latest_block - 1
                    logger.info(f"✨ 首次扫描，起始区块: {last_scanned + 1}")
                
                # 扫描新区块
                scan_count = 0
                for block_num in range(last_scanned + 1, latest_block + 1):
                    await self.scan_block(block_num)
                    scan_count += 1
                    
                    # 避免扫描太快（缩短延迟）
                    await asyncio.sleep(0.2)
                
                # if scan_count > 0:
                #     logger.info(f"✅ 本轮扫描完成，处理了 {scan_count} 个区块 (#{last_scanned + 1} - #{latest_block})")
                
                # 过期旧订单
                expired_count = await self.db.expire_old_orders()
                if expired_count > 0:
                    logger.info(f"⏰ 过期了 {expired_count} 个订单")
                
                # 等待下次扫描
                await asyncio.sleep(self.scan_interval)
                
            except Exception as e:
                logger.error(f"扫描循环错误: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await asyncio.sleep(self.scan_interval)
    
    def stop_scanning(self) -> None:
        """停止扫描"""
        self.is_running = False
        logger.info("扫描器已停止")


class RechargeModule:
    """充值模块"""
    
    def __init__(self, bot_instance):
        """
        初始化充值模块
        
        Args:
            bot_instance: Bot实例
        """
        self.bot = bot_instance
        self.client = bot_instance.client
        self.db = bot_instance.db
        
        # 初始化扫描器，传入自己以便回调通知
        self.scanner = TronBlockScanner(self.db, self)
        
        # 初始化VIP模块
        from vip import VIPModule
        self.vip_module = VIPModule(self.client, self.db)
        
        # 扫描任务
        self.scan_task = None
        
        # 用户订单消息ID字典（用于编辑消息）
        self.user_order_messages = {}
        
        logger.info("充值模块已加载")
    
    async def notify_recharge_success(self, user_id: int, order_id: str, currency: str, 
                                      amount: float, points: float, tx_hash: str):
        """
        通知用户充值成功（编辑订单消息）
        
        Args:
            user_id: 用户ID
            order_id: 订单ID
            currency: 币种
            amount: 充值金额
            points: 获得积分
            tx_hash: 交易哈希
        """
        try:
            # 获取订单信息判断是否为VIP订单
            order = await self.db.get_order_by_id(order_id)
            is_vip_order = order and order.get('order_type') == 'vip'
            vip_months = order.get('vip_months', 0) if order else 0
            
            if is_vip_order and vip_months > 0:
                # VIP订单，激活VIP
                await self.db.activate_vip(user_id, vip_months)
                
                # 获取VIP到期时间
                vip_info = await self.db.get_user_vip_info(user_id)
                expire_str = ""
                if vip_info and vip_info['expire_time']:
                    from datetime import datetime
                    expire_dt = datetime.fromisoformat(vip_info['expire_time'])
                    expire_str = expire_dt.strftime('%Y-%m-%d %H:%M')
                
                # 获取VIP配额配置
                monthly_quota = int(await self.db.get_config('vip_monthly_query_limit', '3999'))
                
                # 准备VIP开通成功消息
                success_message = (
                    f'🎉 <b>VIP开通成功！</b>\n\n'
                    f'<b>订单号:</b> <code>{order_id}</code>\n'
                    f'<b>支付币种:</b> {currency}\n'
                    f'<b>支付金额:</b> {amount} {currency}\n'
                    f'<b>开通时长:</b> {vip_months} 个月\n'
                    f'📅 <b>到期时间:</b> {expire_str}\n\n'
                    f'<b>交易哈希:</b>\n<code>{tx_hash}</code>\n\n'
                    f'💎 <b>VIP专属权益已激活：</b>\n'
                    f'• 每月 {monthly_quota} 次查询（免积分）\n'
                    f'• 解锁关联用户数据查看功能\n\n'
                    f'✅ 感谢您的支持！'
                )
            else:
                # 普通充值订单
                # 获取用户当前余额
                balance = await self.db.get_balance(user_id)
                balance_str = f'{int(balance)}' if balance == int(balance) else f'{balance:.2f}'
                points_str = f'{int(points)}' if points == int(points) else f'{points:.2f}'
                
                # 准备充值成功消息
                success_message = (
                    f'🎉 <b>充值成功！</b>\n\n'
                    f'<b>订单号:</b> <code>{order_id}</code>\n'
                    f'<b>充值币种:</b> {currency}\n'
                    f'<b>充值金额:</b> {amount} {currency}\n'
                    f'<b>获得积分:</b> <code>{points_str}</code> 积分\n\n'
                    f'💰 <b>当前余额:</b> <code>{balance_str}</code> 积分\n\n'
                    f'<b>交易哈希:</b>\n<code>{tx_hash}</code>\n\n'
                    f'✅ 积分已到账，感谢充值！'
                )
            
            # 获取订单消息ID
            message_id = self.user_order_messages.get(user_id)
            
            if message_id:
                # 编辑原订单消息
                try:
                    await self.client.edit_message(
                        user_id, message_id,
                        success_message,
                        buttons=None,
                        parse_mode='html'
                    )
                    # 清除消息ID记录
                    del self.user_order_messages[user_id]
                except Exception as edit_error:
                    # 如果编辑失败，发送新消息
                    logger.warning(f"编辑充值成功消息失败，改为发送新消息: {edit_error}")
                    await self.client.send_message(user_id, success_message, parse_mode='html')
            else:
                # 没有消息ID，发送新消息
                await self.client.send_message(user_id, success_message, parse_mode='html')
            
            logger.info(f"已通知用户 {user_id} 充值成功")
        except Exception as e:
            logger.error(f"通知用户充值成功失败: {e}")
    
    async def start_scanner(self) -> None:
        """启动扫描器"""
        if not config.RECHARGE_WALLET_ADDRESS:
            logger.warning("未配置充值钱包地址，充值功能未启动")
            return
        
        if not self.scan_task or self.scan_task.done():
            self.scan_task = asyncio.create_task(self.scanner.start_scanning())
            logger.info("充值扫描器已启动")
    
    async def stop_scanner(self) -> None:
        """停止扫描器"""
        self.scanner.stop_scanning()
        if self.scan_task and not self.scan_task.done():
            self.scan_task.cancel()
            try:
                await self.scan_task
            except asyncio.CancelledError:
                pass
        logger.info("充值扫描器已停止")
    
    def register_handlers(self) -> None:
        """注册充值相关的命令处理器"""
        from telethon import events, Button
        
        # 用户状态字典（等待输入金额）
        user_states = {}
        
        @self.client.on(events.CallbackQuery(pattern=r'^recharge_start$'))
        async def recharge_start_handler(event):
            """处理充值按钮（从个人中心进入）"""
            user_id = event.sender_id
            
            try:
                # 检查充值功能是否启用
                if not config.RECHARGE_WALLET_ADDRESS:
                    await event.answer('❌ 充值功能暂未开放', alert=True)
                    return
                
                # 检查是否已有活跃订单
                active_order = await self.db.get_active_order(user_id)
                
                if active_order:
                    # 显示现有订单
                    await event.answer()
                    await self._show_order_info_edit(event, active_order)
                    return
                
                await event.answer()
                
                # 显示充值选项
                buttons = [
                    [Button.inline('💳 积分充值', 'recharge_points_menu')],
                    [Button.inline('💎 VIP开通', 'vip_menu')],
                    [Button.inline('« 返回主菜单', 'cmd_back_to_start')]
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
                
            except Exception as e:
                logger.error(f"充值按钮处理失败: {e}")
                await event.answer('❌ 操作失败', alert=True)
        
        @self.client.on(events.CallbackQuery(pattern=r'^recharge_points_menu$'))
        async def recharge_points_menu_handler(event):
            """显示积分充值菜单"""
            try:
                await event.answer()
                
                # 显示积分充值选项
                buttons = [
                    [Button.inline('💎 USDT充值', 'recharge_usdt')],
                    [Button.inline('💵 TRX充值', 'recharge_trx')],
                    [Button.inline('« 返回', 'recharge_start')]
                ]
                
                # 获取最小充值金额
                min_amount = float(await self.db.get_config('recharge_min_amount', '10'))
                
                await event.edit(
                    '💳 <b>积分充值</b>\n\n'
                    f'最小充值金额: <code>{min_amount}</code> USDT\n\n'
                    '请选择您要使用的充值币种：',
                    buttons=buttons,
                    parse_mode='html'
                )
                
            except Exception as e:
                logger.error(f"显示积分充值菜单失败: {e}")
                await event.answer('❌ 操作失败', alert=True)
        
        @self.client.on(events.NewMessage(pattern=r'^/recharge$'))
        async def recharge_handler(event):
            """充值命令"""
            user_id = event.sender_id
            
            try:
                # 检查充值功能是否启用
                if not config.RECHARGE_WALLET_ADDRESS:
                    await event.respond('❌ 充值功能暂未开放')
                    return
                
                # 检查是否已有活跃订单
                active_order = await self.db.get_active_order(user_id)
                
                if active_order:
                    # 显示现有订单
                    await self._show_order_info(event, active_order)
                    return
                
                # 显示充值选项
                buttons = [
                    [Button.inline('💎 USDT充值', 'recharge_usdt')],
                    [Button.inline('💵 TRX充值', 'recharge_trx')]
                ]
                
                # 获取最小充值金额
                min_amount = float(await self.db.get_config('recharge_min_amount', '10'))
                
                await event.respond(
                    '💳 <b>选择充值方式</b>\n\n'
                    f'最小充值金额: <code>{min_amount}</code>\n\n'
                    '请选择您要使用的充值币种：',
                    buttons=buttons,
                    parse_mode='html'
                )
                
            except Exception as e:
                logger.error(f"充值命令处理失败: {e}")
                await event.respond('❌ 操作失败，请稍后重试')
        
        @self.client.on(events.CallbackQuery(pattern=r'^recharge_(usdt|trx)$'))
        async def recharge_currency_handler(event):
            """选择充值币种"""
            try:
                currency = event.data.decode('utf-8').split('_')[1].upper()
                user_id = event.sender_id
                
                await event.answer()
                
                # 获取最小充值金额
                min_amount = float(await self.db.get_config('recharge_min_amount', '10'))
                
                # 添加返回按钮
                buttons = [
                    [Button.inline('« 返回', 'recharge_start')]
                ]
                
                await event.edit(
                    f'💰 <b>{currency}充值</b>\n\n'
                    f'<b>最小金额:</b> <code>{min_amount}</code> {currency}\n\n'
                    f'💡 <b>请回复此消息输入充值金额</b>\n'
                    f'示例: 回复 <code>100</code>',
                    buttons=buttons,
                    parse_mode='html'
                )
                
                # 保存用户状态和消息ID
                user_states[user_id] = {
                    'currency': currency, 
                    'waiting_amount': True,
                    'message_id': event.message_id
                }
                
            except Exception as e:
                logger.error(f"选择充值币种失败: {e}")
                await event.answer('❌ 操作失败', alert=True)
        
        @self.client.on(events.NewMessage())
        async def amount_input_handler(event):
            """处理金额输入"""
            user_id = event.sender_id
            
            # 检查用户是否在等待输入金额
            if user_id not in user_states or not user_states[user_id].get('waiting_amount'):
                return
            
            # 检查是否回复了充值消息
            if not event.is_reply:
                return
            
            # 检查回复的消息ID是否匹配
            reply_to_msg_id = event.reply_to_msg_id
            expected_msg_id = user_states[user_id].get('message_id')
            
            if reply_to_msg_id != expected_msg_id:
                return
            
            try:
                # 删除用户输入的消息
                try:
                    await event.delete()
                except:
                    pass
                
                # 解析金额
                amount_text = event.text.strip()
                
                try:
                    amount = float(amount_text)
                except ValueError:
                    # 编辑之前的消息显示错误
                    message_id = user_states[user_id].get('message_id')
                    currency = user_states[user_id]['currency']
                    if message_id:
                        buttons = [[Button.inline('« 返回', 'recharge_start')]]
                        await self.client.edit_message(
                            user_id, message_id,
                            f'❌ <b>金额格式错误</b>\n\n请回复此消息输入正确的数字\n\n💡 <b>示例:</b> 回复 <code>100</code>',
                            buttons=buttons,
                            parse_mode='html'
                        )
                    return
                
                # 获取配置
                min_amount = float(await self.db.get_config('recharge_min_amount', '10'))
                
                if amount < min_amount:
                    message_id = user_states[user_id].get('message_id')
                    if message_id:
                        buttons = [[Button.inline('« 返回', 'recharge_start')]]
                        await self.client.edit_message(
                            user_id, message_id,
                            f'❌ <b>金额过小</b>\n\n最小充值金额: <code>{min_amount}</code>\n\n请回复此消息重新输入',
                            buttons=buttons,
                            parse_mode='html'
                        )
                    return
                
                if amount > 1000000:
                    message_id = user_states[user_id].get('message_id')
                    if message_id:
                        buttons = [[Button.inline('« 返回', 'recharge_start')]]
                        await self.client.edit_message(
                            user_id, message_id,
                            '❌ <b>金额过大</b>\n\n大额充值请联系管理员',
                            buttons=buttons,
                            parse_mode='html'
                        )
                    return
                
                currency = user_states[user_id]['currency']
                message_id = user_states[user_id].get('message_id')
                
                # 分配金额标识（传入币种）
                actual_amount = await self.db.allocate_amount_identifier(amount, currency)
                
                if not actual_amount:
                    if message_id:
                        buttons = [[Button.inline('« 返回', 'recharge_start')]]
                        await self.client.edit_message(
                            user_id, message_id,
                            '❌ <b>系统繁忙</b>\n\n当前充值订单较多，请稍后重试',
                            buttons=buttons,
                            parse_mode='html'
                        )
                    return
                
                # 创建订单
                timeout = int(await self.db.get_config('recharge_timeout', '1800'))
                expired_at = (datetime.now() + timedelta(seconds=timeout)).isoformat()
                
                order_id = await self.db.create_recharge_order(
                    user_id, currency, amount, actual_amount,
                    config.RECHARGE_WALLET_ADDRESS, expired_at
                )
                
                if not order_id:
                    await self.db.release_identifier(actual_amount, currency)
                    if message_id:
                        buttons = [[Button.inline('« 返回', 'recharge_start')]]
                        await self.client.edit_message(
                            user_id, message_id,
                            '❌ <b>创建订单失败</b>\n\n请稍后重试',
                            buttons=buttons,
                            parse_mode='html'
                        )
                    return
                
                # 保存订单消息ID（用于充值到账时编辑）
                self.user_order_messages[user_id] = message_id
                
                # 清除用户状态
                del user_states[user_id]
                
                # 计算应获得的积分（基于实际需转账金额）
                if currency == 'USDT':
                    points = await exchange_manager.usdt_to_points(actual_amount)
                else:
                    points = await exchange_manager.trx_to_points(actual_amount)
                
                # 显示订单信息（编辑消息）
                remaining_minutes = timeout // 60
                
                buttons = [[Button.inline('❌ 取消订单', f'cancel_order_{order_id}')]]
                
                if message_id:
                    await self.client.edit_message(
                        user_id, message_id,
                        f'✅ <b>订单创建成功</b>\n\n'
                        f'<b>订单号:</b> <code>{order_id}</code>\n'
                        f'<b>币种:</b> {currency}\n'
                        f'<b>充值金额:</b> {actual_amount} {currency}\n'
                        f'<b>到账积分:</b> <code>{points:.2f}</code> 积分\n\n'
                        f'━━━━━━━━━━━━━━━━━━\n\n'
                        f'<b>⚠️ 请务必转账以下准确金额：</b>\n'
                        f'<code>{actual_amount}</code> {currency}\n\n'
                        f'<b>收款地址：</b>\n'
                        f'<code>{config.RECHARGE_WALLET_ADDRESS}</code>\n\n'
                        f'━━━━━━━━━━━━━━━━━━\n\n'
                        f'⏰ 订单有效期: <b>{remaining_minutes}</b> 分钟\n'
                        f'💡 转账后约 <b>13秒</b> 内自动到账\n\n'
                        f'⚠️ <b>重要提示：</b>\n'
                        f'• 必须转账准确金额 <code>{actual_amount}</code>\n'
                        f'• 包括小数部分\n'
                        f'• 金额错误将无法自动到账',
                        buttons=buttons,
                        parse_mode='html'
                    )
                
                logger.info(f"用户 {user_id} 创建充值订单: {order_id}, {actual_amount} {currency}")
                
            except Exception as e:
                logger.error(f"处理金额输入失败: {e}")
                await event.respond('❌ 操作失败，请重试')
                if user_id in user_states:
                    del user_states[user_id]
        
        @self.client.on(events.CallbackQuery(pattern=r'^cancel_order_'))
        async def cancel_order_handler(event):
            """取消订单"""
            try:
                await event.answer()
                
                order_id = event.data.decode('utf-8').replace('cancel_order_', '')
                
                # 验证订单所有权
                order = await self.db.get_active_order(event.sender_id)
                
                if not order or order['order_id'] != order_id:
                    await event.answer('❌ 订单不存在或已过期', alert=True)
                    return
                
                # 取消订单
                success = await self.db.cancel_order(order_id)
                
                if success:
                    await event.edit(
                        '✅ <b>订单已取消</b>\n\n'
                        '金额标识已释放，您可以重新创建订单。',
                        parse_mode='html'
                    )
                    logger.info(f"用户 {event.sender_id} 取消订单: {order_id}")
                else:
                    await event.answer('❌ 取消失败', alert=True)
                    
            except Exception as e:
                logger.error(f"取消订单失败: {e}")
                await event.answer('❌ 操作失败', alert=True)
        
        # 注册VIP回调处理
        @self.client.on(events.CallbackQuery(pattern=r'^vip_'))
        async def vip_callback_handler(event):
            """处理VIP相关回调"""
            try:
                await self.vip_module.handle_vip_callback(event)
            except Exception as e:
                logger.error(f"VIP回调处理失败: {e}")
                await event.answer('❌ 操作失败', alert=True)
        
        logger.info("充值命令处理器已注册")
    
    async def _show_order_info(self, event, order: Dict) -> None:
        """显示订单信息"""
        currency = order['currency']
        amount = order['amount']
        actual_amount = order['actual_amount']
        wallet = order['wallet_address']
        created_at = order['created_at']
        expired_at = order['expired_at']
        
        # 固定显示30分钟
        remaining_minutes = 30
        
        buttons = [
            [Button.inline('取消订单', f"cancel_order_{order['order_id']}")],
            [Button.inline('« 返回主菜单', 'cmd_back_to_start')]
        ]
        
        await event.respond(
            f'📋 <b>充值订单</b>\n\n'
            f'<b>订单号:</b> <code>{order["order_id"]}</code>\n'
            f'<b>币种:</b> {currency}\n'
            f'<b>原始金额:</b> {amount} {currency}\n'
            f'<b>实际支付:</b> <code>{actual_amount}</code> {currency}\n\n'
            f'<b>收款地址:</b>\n<code>{wallet}</code>\n\n'
            f'⏰ <b>剩余时间:</b> {remaining_minutes} 分钟\n\n'
            f'💡 <b>请务必转账准确金额 {actual_amount}，否则无法自动到账！</b>',
            buttons=buttons,
            parse_mode='html'
        )
    
    async def _show_order_info_edit(self, event, order: Dict) -> None:
        """显示订单信息（编辑消息）"""
        currency = order['currency']
        amount = order['amount']
        actual_amount = order['actual_amount']
        wallet = order['wallet_address']
        created_at = order['created_at']
        expired_at = order['expired_at']
        
        # 固定显示30分钟
        remaining_minutes = 30
        
        buttons = [
            [Button.inline('❌ 取消订单', f"cancel_order_{order['order_id']}")],
            [Button.inline('« 返回', 'recharge_start')]
        ]
        
        await event.edit(
            f'📋 <b>充值订单</b>\n\n'
            f'<b>订单号:</b> <code>{order["order_id"]}</code>\n'
            f'<b>币种:</b> {currency}\n'
            f'<b>原始金额:</b> {amount} {currency}\n'
            f'<b>实际支付:</b> <code>{actual_amount}</code> {currency}\n\n'
            f'<b>收款地址:</b>\n<code>{wallet}</code>\n\n'
            f'⏰ <b>剩余时间:</b> {remaining_minutes} 分钟\n\n'
            f'💡 <b>请务必转账准确金额 {actual_amount}，否则无法自动到账！</b>',
            buttons=buttons,
            parse_mode='html'
        )

