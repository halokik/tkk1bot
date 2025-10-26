"""
汇率转换模块 - 处理加密货币与积分的兑换
积分内部对应人民币，用于未来的充值功能
"""
import aiohttp
import logging
from typing import Optional, Dict
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ExchangeRateManager:
    """汇率管理器"""
    
    def __init__(self):
        """初始化汇率管理器"""
        # Binance API 端点
        self.binance_api = "https://api.binance.com/api/v3/ticker/price"
        
        # 汇率缓存（避免频繁请求API）
        self.rate_cache = {}
        self.cache_expire_time = {}
        self.cache_duration = 300  # 缓存5分钟
        
        # 固定汇率配置（当API失败时使用）
        self.fixed_rates = {
            'USDT_CNY': 7.2,    # 1 USDT ≈ 7.2 人民币
            'TRX_CNY': 0.75,    # 1 TRX ≈ 0.75 人民币（可手动调整）
            'USDT_POINTS': 7.2,  # 1 USDT = 7.2 积分
            'TRX_POINTS': 0.75,  # 1 TRX = 0.75 积分
        }
        
        # 是否启用API（False则只使用固定汇率）
        self.use_api = True
        
        logger.info("汇率管理器已初始化")
    
    def set_fixed_rate(self, currency: str, rate: float):
        """
        设置固定汇率
        
        Args:
            currency: 货币类型 ('USDT' 或 'TRX')
            rate: 汇率值（相对于积分）
        """
        key_cny = f'{currency}_CNY'
        key_points = f'{currency}_POINTS'
        
        self.fixed_rates[key_cny] = rate
        self.fixed_rates[key_points] = rate
        
        logger.info(f"固定汇率已设置: 1 {currency} = {rate} 积分")
    
    def enable_api(self, enabled: bool = True):
        """
        启用或禁用API查询
        
        Args:
            enabled: True启用API，False只使用固定汇率
        """
        self.use_api = enabled
        logger.info(f"API查询已{'启用' if enabled else '禁用'}")
    
    async def _fetch_binance_price(self, symbol: str) -> Optional[float]:
        """
        从Binance获取价格
        
        Args:
            symbol: 交易对符号（如 USDTCNY, TRXUSDT）
        
        Returns:
            价格，失败返回None
        """
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                params = {'symbol': symbol}
                async with session.get(self.binance_api, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = float(data.get('price', 0))
                        if price > 0:
                            logger.debug(f"Binance {symbol} 价格: {price}")
                            return price
                    else:
                        logger.warning(f"Binance API 返回状态码: {response.status}")
        except asyncio.TimeoutError:
            logger.warning(f"Binance API 请求超时: {symbol}")
        except Exception as e:
            logger.error(f"获取Binance价格失败 {symbol}: {e}")
        
        return None
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self.cache_expire_time:
            return False
        return datetime.now() < self.cache_expire_time[key]
    
    def _set_cache(self, key: str, value: float):
        """设置缓存"""
        self.rate_cache[key] = value
        self.cache_expire_time[key] = datetime.now() + timedelta(seconds=self.cache_duration)
    
    async def get_usdt_rate(self) -> float:
        """
        获取USDT汇率（USDT → 积分）
        1 USDT = ? 积分
        
        Returns:
            汇率值
        """
        cache_key = 'USDT_POINTS'
        
        # 检查缓存
        if self._is_cache_valid(cache_key):
            return self.rate_cache[cache_key]
        
        # 如果禁用API，直接返回固定汇率
        if not self.use_api:
            return self.fixed_rates['USDT_POINTS']
        
        try:
            # Binance 可能没有 USDTCNY 直接交易对
            # 可以通过其他方式计算，这里暂时使用固定汇率
            # 实际场景中可以通过 USDT/USD * USD/CNY 计算
            
            rate = self.fixed_rates['USDT_POINTS']
            self._set_cache(cache_key, rate)
            return rate
            
        except Exception as e:
            logger.error(f"获取USDT汇率失败: {e}")
            return self.fixed_rates['USDT_POINTS']
    
    async def get_trx_rate(self) -> float:
        """
        获取TRX汇率（TRX → 积分）
        1 TRX = ? 积分
        
        Returns:
            汇率值
        """
        cache_key = 'TRX_POINTS'
        
        # 检查缓存
        if self._is_cache_valid(cache_key):
            return self.rate_cache[cache_key]
        
        # 如果禁用API，直接返回固定汇率
        if not self.use_api:
            return self.fixed_rates['TRX_POINTS']
        
        try:
            # 获取 TRX/USDT 价格
            trx_usdt = await self._fetch_binance_price('TRXUSDT')
            
            if trx_usdt:
                # 获取 USDT 汇率
                usdt_rate = await self.get_usdt_rate()
                
                # 计算 TRX → 积分
                # 1 TRX = X USDT
                # 1 USDT = Y 积分
                # 所以 1 TRX = X * Y 积分
                rate = trx_usdt * usdt_rate
                
                self._set_cache(cache_key, rate)
                logger.info(f"TRX实时汇率: 1 TRX = {rate:.4f} 积分")
                return rate
            else:
                # API失败，使用固定汇率
                logger.warning("TRX价格获取失败，使用固定汇率")
                rate = self.fixed_rates['TRX_POINTS']
                self._set_cache(cache_key, rate)
                return rate
                
        except Exception as e:
            logger.error(f"获取TRX汇率失败: {e}")
            return self.fixed_rates['TRX_POINTS']
    
    async def usdt_to_points(self, usdt_amount: float) -> float:
        """
        USDT转换为积分
        
        Args:
            usdt_amount: USDT数量
        
        Returns:
            积分数量
        """
        rate = await self.get_usdt_rate()
        points = usdt_amount * rate
        logger.info(f"兑换: {usdt_amount} USDT → {points:.2f} 积分")
        return points
    
    async def trx_to_points(self, trx_amount: float) -> float:
        """
        TRX转换为积分
        
        Args:
            trx_amount: TRX数量
        
        Returns:
            积分数量
        """
        rate = await self.get_trx_rate()
        points = trx_amount * rate
        logger.info(f"兑换: {trx_amount} TRX → {points:.2f} 积分")
        return points
    
    async def points_to_usdt(self, points_amount: float) -> float:
        """
        积分转换为USDT
        
        Args:
            points_amount: 积分数量
        
        Returns:
            USDT数量
        """
        rate = await self.get_usdt_rate()
        usdt = points_amount / rate
        return usdt
    
    async def points_to_trx(self, points_amount: float) -> float:
        """
        积分转换为TRX
        
        Args:
            points_amount: 积分数量
        
        Returns:
            TRX数量
        """
        rate = await self.get_trx_rate()
        trx = points_amount / rate
        return trx

    async def usdt_to_trx(self, usdt_amount: float) -> float:
        """
        USDT 转 TRX（通过积分基准互转）
        """
        usdt_rate = await self.get_usdt_rate()
        trx_rate = await self.get_trx_rate()
        # 1 USDT = usdt_rate points, 1 TRX = trx_rate points
        # USDT → TRX 比例 = usdt_rate / trx_rate
        return usdt_amount * (usdt_rate / trx_rate)

    async def trx_to_usdt(self, trx_amount: float) -> float:
        """
        TRX 转 USDT（通过积分基准互转）
        """
        usdt_rate = await self.get_usdt_rate()
        trx_rate = await self.get_trx_rate()
        # TRX → USDT 比例 = trx_rate / usdt_rate
        return trx_amount * (trx_rate / usdt_rate)
    
    async def get_rate_info(self) -> Dict[str, float]:
        """
        获取当前所有汇率信息
        
        Returns:
            汇率信息字典
        """
        usdt_rate = await self.get_usdt_rate()
        trx_rate = await self.get_trx_rate()
        
        return {
            'usdt_to_points': usdt_rate,
            'trx_to_points': trx_rate,
            'points_to_usdt': 1 / usdt_rate,
            'points_to_trx': 1 / trx_rate,
            'using_api': self.use_api,
            'cache_duration': self.cache_duration
        }
    
    def clear_cache(self):
        """清除汇率缓存"""
        self.rate_cache.clear()
        self.cache_expire_time.clear()
        logger.info("汇率缓存已清除")


# 全局实例
exchange_manager = ExchangeRateManager()

