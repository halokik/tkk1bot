"""
汇率模块测试脚本
测试 exchange.py 的各项功能
"""
import asyncio
import logging
from exchange import exchange_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_exchange():
    """测试汇率功能"""
    
    print("\n" + "="*60)
    print("汇率模块测试")
    print("="*60 + "\n")
    
    # 测试1: 获取默认汇率
    print("📊 测试1: 获取默认汇率")
    print("-" * 60)
    usdt_rate = await exchange_manager.get_usdt_rate()
    trx_rate = await exchange_manager.get_trx_rate()
    print(f"✅ USDT汇率: 1 USDT = {usdt_rate:.4f} 积分")
    print(f"✅ TRX汇率: 1 TRX = {trx_rate:.4f} 积分")
    
    # 测试2: 货币转换
    print("\n💱 测试2: 货币转换")
    print("-" * 60)
    
    usdt_amount = 10
    points_from_usdt = await exchange_manager.usdt_to_points(usdt_amount)
    print(f"✅ {usdt_amount} USDT → {points_from_usdt:.2f} 积分")
    
    trx_amount = 100
    points_from_trx = await exchange_manager.trx_to_points(trx_amount)
    print(f"✅ {trx_amount} TRX → {points_from_trx:.2f} 积分")
    
    # 测试3: 反向转换
    print("\n🔄 测试3: 反向转换")
    print("-" * 60)
    
    points_amount = 100
    usdt_from_points = await exchange_manager.points_to_usdt(points_amount)
    trx_from_points = await exchange_manager.points_to_trx(points_amount)
    print(f"✅ {points_amount} 积分 → {usdt_from_points:.4f} USDT")
    print(f"✅ {points_amount} 积分 → {trx_from_points:.4f} TRX")
    
    # 测试4: 设置固定汇率
    print("\n⚙️  测试4: 设置固定汇率")
    print("-" * 60)
    
    exchange_manager.set_fixed_rate('USDT', 7.0)
    exchange_manager.set_fixed_rate('TRX', 0.8)
    
    # 清除缓存以使用新汇率
    exchange_manager.clear_cache()
    
    new_usdt_rate = await exchange_manager.get_usdt_rate()
    new_trx_rate = await exchange_manager.get_trx_rate()
    print(f"✅ 新USDT汇率: 1 USDT = {new_usdt_rate:.4f} 积分")
    print(f"✅ 新TRX汇率: 1 TRX = {new_trx_rate:.4f} 积分")
    
    # 测试5: API开关
    print("\n🔌 测试5: API开关")
    print("-" * 60)
    
    exchange_manager.enable_api(False)
    print("✅ API已禁用，使用固定汇率")
    
    exchange_manager.enable_api(True)
    print("✅ API已启用，尝试获取实时汇率")
    
    # 测试6: 获取完整汇率信息
    print("\n📋 测试6: 完整汇率信息")
    print("-" * 60)
    
    rate_info = await exchange_manager.get_rate_info()
    print(f"USDT → 积分: {rate_info['usdt_to_points']:.4f}")
    print(f"TRX → 积分: {rate_info['trx_to_points']:.4f}")
    print(f"积分 → USDT: {rate_info['points_to_usdt']:.4f}")
    print(f"积分 → TRX: {rate_info['points_to_trx']:.4f}")
    print(f"使用API: {rate_info['using_api']}")
    print(f"缓存时长: {rate_info['cache_duration']}秒")
    
    # 测试7: 充值模拟
    print("\n💳 测试7: 充值模拟")
    print("-" * 60)
    
    # 恢复默认汇率
    exchange_manager.set_fixed_rate('USDT', 7.2)
    exchange_manager.set_fixed_rate('TRX', 0.75)
    exchange_manager.clear_cache()
    
    # 模拟USDT充值
    user_usdt = 50
    earned_points_usdt = await exchange_manager.usdt_to_points(user_usdt)
    print(f"📥 用户充值 {user_usdt} USDT")
    print(f"   → 获得 {earned_points_usdt:.2f} 积分")
    
    # 模拟TRX充值
    user_trx = 200
    earned_points_trx = await exchange_manager.trx_to_points(user_trx)
    print(f"📥 用户充值 {user_trx} TRX")
    print(f"   → 获得 {earned_points_trx:.2f} 积分")
    
    print("\n" + "="*60)
    print("✅ 所有测试完成")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(test_exchange())
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

