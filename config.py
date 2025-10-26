"""
配置文件 - 用于管理 Telegram Bot 的配置信息
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Telegram API 配置
try:
    API_ID = int(os.getenv('API_ID', '0'))
except ValueError:
    API_ID = 0

API_HASH = os.getenv('API_HASH', '').strip()
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
#http://95.211.190.114
# 查询API配置
QUERY_API_URL = os.getenv('QUERY_API_URL', 'http://95.211.190.114').strip()
QUERY_API_KEY = os.getenv('QUERY_API_KEY', '').strip()

# 会话配置
SESSION_NAME = os.getenv('SESSION_NAME', 'bot_session')

# 性能优化配置
CONNECTION_RETRIES = 5
REQUEST_RETRIES = 5
TIMEOUT = 10
MAX_CONCURRENT_REQUESTS = 100  # 最大并发请求数

# 管理员配置
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '').strip()
ADMIN_IDS = [int(aid.strip()) for aid in ADMIN_IDS_STR.split(',') if aid.strip().isdigit()] if ADMIN_IDS_STR else []

# 验证配置
if not API_ID or not API_HASH or not BOT_TOKEN:
    print(f"调试信息 - API_ID: {API_ID}, API_HASH: {repr(API_HASH)}, BOT_TOKEN: {repr(BOT_TOKEN[:20] if BOT_TOKEN else '')}")
    raise ValueError("请在 .env 文件中设置 API_ID、API_HASH 和 BOT_TOKEN")

if not QUERY_API_KEY:
    raise ValueError("请在 .env 文件中设置 QUERY_API_KEY")

# ==================== TRON 充值配置 ====================

# 网络选择 (mainnet/nile)
TRON_NETWORK = os.getenv('TRON_NETWORK', 'nile').lower()

# TronGrid API Key (从 https://www.trongrid.io/ 申请)
TRON_API_KEY = os.getenv('TRON_API_KEY', '')

# 网络配置
if TRON_NETWORK == 'mainnet':
    # 主网配置
    TRON_API_URL = 'https://api.trongrid.io'
    USDT_CONTRACT = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'  # 主网USDT合约
else:
    # Nile测试网配置
    TRON_API_URL = 'https://nile.trongrid.io'
    USDT_CONTRACT = 'TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf'  # Nile测试网USDT合约

# 充值钱包地址（接收充值的地址）
RECHARGE_WALLET_ADDRESS = os.getenv('RECHARGE_WALLET_ADDRESS', '')

# 充值订单配置
RECHARGE_ORDER_TIMEOUT = int(os.getenv('RECHARGE_ORDER_TIMEOUT', '1800'))  # 订单超时时间（秒），默认30分钟
RECHARGE_MIN_AMOUNT = float(os.getenv('RECHARGE_MIN_AMOUNT', '10'))  # 最小充值金额

# 功能开关配置
SHOW_RELATED_USERS = os.getenv('SHOW_RELATED_USERS', 'true').lower() in ('true', '1', 'yes', 'on')  # 是否显示关联用户按钮

