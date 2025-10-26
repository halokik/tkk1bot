"""
测试TRON地址转换功能
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_address_conversion():
    """测试地址转换"""
    from recharge import TronBlockScanner
    from database import Database
    
    print("=" * 60)
    print("TRON地址转换测试")
    print("=" * 60)
    
    # 创建扫描器实例（需要db实例，暂时传None用于测试）
    class MockDB:
        pass
    
    scanner = TronBlockScanner(MockDB())
    
    # 测试地址（示例）
    test_addresses = [
        '41eca9bc828a3005b9a3b909f2cc5c2a54794de05f',  # 您的错误日志中的地址
        '410000000000000000000000000000000000000000',  # 测试地址
        '41a614f803b6fd780986a42c78ec9c7f77e6ded13c',  # 另一个测试地址
    ]
    
    print("\n测试地址转换：\n")
    
    for hex_addr in test_addresses:
        try:
            base58_addr = scanner._hex_to_address(hex_addr)
            print(f"✅ HEX:    {hex_addr}")
            print(f"   Base58: {base58_addr}")
            print()
        except Exception as e:
            print(f"❌ 转换失败: {hex_addr}")
            print(f"   错误: {e}")
            print()
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_address_conversion()

