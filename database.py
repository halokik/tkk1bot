"""
高性能数据库模块 - 使用 aiosqlite 异步操作
"""
import aiosqlite
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import config

logger = logging.getLogger(__name__)


class Database:
    """异步数据库操作类"""
    
    def __init__(self, db_path: str = "telegram_cache.db"):
        self.db_path = db_path
        self.db = None
    
    async def connect(self):
        """连接数据库并初始化表"""
        self.db = await aiosqlite.connect(self.db_path)
        # 启用WAL模式提高并发性能
        await self.db.execute("PRAGMA journal_mode=WAL")
        # 启用外键
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()
        logger.info(f"数据库已连接: {self.db_path}")
    
    async def close(self):
        """关闭数据库连接"""
        if self.db:
            await self.db.close()
            logger.info("数据库已关闭")
    
    async def _create_tables(self):
        """创建数据库表"""
        
        # 用户基础信息表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_active INTEGER DEFAULT 1,
                is_bot INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                groups_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data TEXT
            )
        """)
        
        # 姓名历史表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS name_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                date TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # 用户名历史表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS username_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                date TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # 群组表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                username TEXT,
                chat_type TEXT,
                members_count INTEGER
            )
        """)
        
        # 用户-群组关系表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                UNIQUE(user_id, chat_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (chat_id) REFERENCES groups(chat_id) ON DELETE CASCADE
            )
        """)
        
        # 消息表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                text TEXT,
                date TEXT,
                UNIQUE(chat_id, message_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (chat_id) REFERENCES groups(chat_id) ON DELETE CASCADE
            )
        """)
        
        # 查询日志表（用于统计：用户查询）
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queried_user TEXT NOT NULL,
                querier_user_id INTEGER NOT NULL,
                query_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                from_cache INTEGER DEFAULT 0
            )
        """)
        
        # 关键词查询日志表（用于统计：关键词搜索）
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS text_query_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                query_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                from_cache INTEGER DEFAULT 0
            )
        """)
        
        # 用户余额表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_balance (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                total_earned REAL DEFAULT 0.0,
                total_spent REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 签到记录表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS checkin_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                checkin_date DATE NOT NULL,
                reward REAL NOT NULL,
                checkin_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, checkin_date)
            )
        """)
        
        # 余额变动日志表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS balance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                change_amount REAL NOT NULL,
                balance_before REAL NOT NULL,
                balance_after REAL NOT NULL,
                change_type TEXT NOT NULL,
                description TEXT,
                operator_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 系统配置表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 隐藏用户表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS hidden_users (
                user_identifier TEXT PRIMARY KEY,
                hidden_by INTEGER NOT NULL,
                hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reason TEXT
            )
        """)
        
        # 邀请记录表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER NOT NULL,
                invitee_id INTEGER NOT NULL,
                invitee_username TEXT,
                reward REAL NOT NULL,
                invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(invitee_id)
            )
        """)
        
        # 充值订单表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS recharge_orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                currency TEXT NOT NULL,
                amount REAL NOT NULL,
                actual_amount REAL NOT NULL,
                base_amount REAL,
                identifier REAL,
                points REAL DEFAULT 0,
                status TEXT NOT NULL,
                order_type TEXT DEFAULT 'recharge',
                vip_months INTEGER DEFAULT 0,
                wallet_address TEXT NOT NULL,
                tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expired_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        # 兼容既有表：补充缺失列
        try:
            cursor = await self.db.execute("PRAGMA table_info(recharge_orders)")
            cols = [row[1] for row in await cursor.fetchall()]
            await cursor.close()
            async def ensure_col(name: str, ddl: str):
                if name not in cols:
                    await self.db.execute(f"ALTER TABLE recharge_orders ADD COLUMN {ddl}")
            # 缺失列补齐
            await ensure_col('actual_amount', 'actual_amount REAL DEFAULT 0')
            await ensure_col('base_amount', 'base_amount REAL')
            await ensure_col('identifier', 'identifier REAL')
            await ensure_col('points', 'points REAL DEFAULT 0')
            await ensure_col('order_type', "order_type TEXT DEFAULT 'recharge'")
            await ensure_col('vip_months', 'vip_months INTEGER DEFAULT 0')
            await self.db.commit()
        except Exception as e:
            logger.warning(f"兼容旧版recharge_orders表时出错: {e}")
        
        # 金额标识表（用于分配唯一的充值金额）
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS amount_identifiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'TRX',
                is_used INTEGER DEFAULT 0,
                order_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                released_at TIMESTAMP,
                UNIQUE(identifier, currency)
            )
        """)
        
        # 添加currency字段（如果表已存在但没有该字段）
        try:
            await self.db.execute("ALTER TABLE amount_identifiers ADD COLUMN currency TEXT NOT NULL DEFAULT 'TRX'")
            logger.info("已为amount_identifiers表添加currency字段")
        except:
            pass  # 字段已存在
        
        # 区块扫描记录表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS block_scan_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                currency TEXT NOT NULL,
                block_number INTEGER NOT NULL,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(currency, block_number)
            )
        """)
        
        # 文本搜索缓存表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS text_search_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL UNIQUE,
                total INTEGER NOT NULL,
                results_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 关联用户缓存表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS related_users_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                total INTEGER NOT NULL,
                results_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 客服账号表（支持多个）
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS service_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # VIP用户表
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users_vip (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                expire_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # VIP查询使用记录表（每日重置）
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS vip_query_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query_type TEXT NOT NULL,
                usage_date DATE NOT NULL,
                used_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, query_type, usage_date)
            )
        """)
        
        # 插入默认配置
        await self.db.execute("""
            INSERT OR IGNORE INTO system_config (config_key, config_value, description)
            VALUES 
                ('checkin_min', '1', '签到最小奖励'),
                ('checkin_max', '5', '签到最大奖励'),
                ('text_search_cost', '1', '关键词查询费用'),
                ('query_cost', '1', '查询费用'),
                ('invite_reward', '1', '邀请奖励'),
                ('recharge_timeout', '1800', '充值订单超时时间(秒)'),
                ('recharge_min_amount', '10', '最小充值金额'),
                ('vip_monthly_price', '200', 'VIP月价格(积分)'),
                ('vip_daily_user_query', '50', 'VIP每日用户查询次数'),
                ('vip_daily_text_query', '50', 'VIP每日关键词查询次数'),
                ('fixed_rate_usdt_points', '7.2', '固定汇率: 1 USDT = ? 积分'),
                ('fixed_rate_trx_points', '0.75', '固定汇率: 1 TRX = ? 积分'),
                ('points_per_usdt', '10', '积分兑换USDT汇率'),
                ('trx_to_usdt_rate', '0.1', 'TRX兑USDT汇率')
        """)
        
        # 创建索引提高查询性能
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username 
            ON users(username)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_name_history_user_id 
            ON name_history(user_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user_id 
            ON messages(user_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_query_logs_time 
            ON query_logs(query_time)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_query_logs_querier 
            ON query_logs(querier_user_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_checkin_records_user 
            ON checkin_records(user_id, checkin_date)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_balance_logs_user 
            ON balance_logs(user_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_invitations_inviter 
            ON invitations(inviter_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_invitations_invitee 
            ON invitations(invitee_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_recharge_orders_user 
            ON recharge_orders(user_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_recharge_orders_status 
            ON recharge_orders(status)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_amount_identifiers_used 
            ON amount_identifiers(is_used)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_block_scan_currency 
            ON block_scan_records(currency)
        """)
        
        await self.db.commit()
        logger.info("数据库表已初始化")

    async def get_service_accounts(self) -> List[str]:
        """获取已设置的客服账号列表（username）"""
        try:
            cursor = await self.db.execute(
                "SELECT username FROM service_accounts ORDER BY id ASC"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"获取客服账号列表失败: {e}")
            return []

    async def add_service_accounts(self, usernames: List[str], added_by: int = None) -> Dict[str, int]:
        """
        批量添加客服账号（去重，忽略已存在）
        Returns: {added: int, skipped: int}
        """
        try:
            added = 0
            skipped = 0
            for name in usernames:
                try:
                    await self.db.execute(
                        "INSERT OR IGNORE INTO service_accounts (username, added_by) VALUES (?, ?)",
                        (name, added_by)
                    )
                    # 判断是否插入成功（lastrowid在IGNORE时为0/None）
                    # aiosqlite的lastrowid不可靠，这里额外查询判断
                    cursor = await self.db.execute(
                        "SELECT 1 FROM service_accounts WHERE username = ?",
                        (name,)
                    )
                    exists = await cursor.fetchone()
                    await cursor.close()
                    # 如果存在且是新插入也为True，这里简单统计：若先查存在就当作跳过
                    # 为更准确，改为先查是否存在
                except Exception:
                    pass
                # 先查存在再插入，避免统计不准确
            added = 0
            skipped = 0
            for name in set(usernames):
                cursor = await self.db.execute(
                    "SELECT 1 FROM service_accounts WHERE username = ?",
                    (name,)
                )
                exists = await cursor.fetchone()
                await cursor.close()
                if exists:
                    skipped += 1
                else:
                    await self.db.execute(
                        "INSERT INTO service_accounts (username, added_by) VALUES (?, ?)",
                        (name, added_by)
                    )
                    added += 1
            await self.db.commit()
            return {"added": added, "skipped": skipped}
        except Exception as e:
            logger.error(f"添加客服账号失败: {e}")
            await self.db.rollback()
            return {"added": 0, "skipped": 0}

    async def clear_service_accounts(self) -> int:
        """清空客服账号，返回清除数量"""
        try:
            cursor = await self.db.execute("SELECT COUNT(*) FROM service_accounts")
            row = await cursor.fetchone()
            await cursor.close()
            count = int(row[0] or 0)
            await self.db.execute("DELETE FROM service_accounts")
            await self.db.commit()
            return count
        except Exception as e:
            logger.error(f"清空客服账号失败: {e}")
            return 0
    
    async def save_user_data(self, data: Dict[str, Any]) -> bool:
        """
        保存用户完整数据到数据库
        
        Args:
            data: API返回的完整数据
        
        Returns:
            bool: 是否保存成功
        """
        try:
            user_data = data.get('data', {})
            basic_info = user_data.get('basicInfo', {})
            
            user_id = basic_info.get('id') or user_data.get('userId')
            if not user_id:
                logger.error("用户ID不存在")
                return False
            
            # 保存用户基础信息
            await self.db.execute("""
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, is_active, is_bot, 
                 message_count, groups_count, last_updated, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                basic_info.get('username', ''),
                basic_info.get('first_name', ''),
                basic_info.get('last_name', ''),
                1 if basic_info.get('is_active', True) else 0,
                1 if basic_info.get('is_bot', False) else 0,
                user_data.get('messageCount', 0),
                user_data.get('groupsCount', 0),
                datetime.now().isoformat(),
                json.dumps(data)  # 保存原始数据
            ))
            
            # 清除旧的姓名历史
            await self.db.execute("DELETE FROM name_history WHERE user_id = ?", (user_id,))
            
            # 保存姓名历史
            names = user_data.get('names', [])
            for name_record in names:
                if isinstance(name_record, dict):
                    name = name_record.get('name', '').strip()
                    date = name_record.get('date_time') or name_record.get('date', '')
                    if name:
                        await self.db.execute("""
                            INSERT INTO name_history (user_id, name, date)
                            VALUES (?, ?, ?)
                        """, (user_id, name, date))
            
            # 清除旧的用户名历史
            await self.db.execute("DELETE FROM username_history WHERE user_id = ?", (user_id,))
            
            # 保存用户名历史
            usernames = user_data.get('usernames', [])
            for username_record in usernames:
                if isinstance(username_record, dict):
                    username = username_record.get('username', '').strip()
                    date = username_record.get('date', '')
                    if username:
                        await self.db.execute("""
                            INSERT INTO username_history (user_id, username, date)
                            VALUES (?, ?, ?)
                        """, (user_id, username, date))
            
            # 保存群组信息
            groups = user_data.get('groups', [])
            for group in groups:
                chat = group.get('chat', {})
                chat_id = chat.get('id')
                if chat_id:
                    await self.db.execute("""
                        INSERT OR REPLACE INTO groups 
                        (chat_id, title, username, chat_type, members_count)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        chat_id,
                        chat.get('title', ''),
                        chat.get('username', ''),
                        chat.get('type', ''),
                        chat.get('members_count', 0)
                    ))
                    
                    # 建立用户-群组关系
                    await self.db.execute("""
                        INSERT OR IGNORE INTO user_groups (user_id, chat_id)
                        VALUES (?, ?)
                    """, (user_id, chat_id))
            
            # 保存消息记录
            messages = user_data.get('messages', [])
            for msg in messages:
                chat = msg.get('chat', {})
                chat_id = chat.get('id')
                msg_id = msg.get('id')
                
                if chat_id and msg_id:
                    await self.db.execute("""
                        INSERT OR REPLACE INTO messages 
                        (user_id, chat_id, message_id, text, date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        chat_id,
                        msg_id,
                        msg.get('text', ''),
                        msg.get('date', '')
                    ))
            
            await self.db.commit()
            logger.info(f"用户 {user_id} 数据已保存到数据库")
            return True
            
        except Exception as e:
            logger.error(f"保存用户数据失败: {e}")
            await self.db.rollback()
            return False
    
    async def get_user_data(self, user_identifier: str) -> Optional[Dict[str, Any]]:
        """
        从数据库获取用户数据
        
        Args:
            user_identifier: 用户ID或用户名
        
        Returns:
            Dict: 用户数据（API格式）或None
        """
        try:
            # 尝试按用户ID查询
            if user_identifier.isdigit():
                cursor = await self.db.execute(
                    "SELECT * FROM users WHERE user_id = ?",
                    (int(user_identifier),)
                )
            else:
                # 按用户名查询
                cursor = await self.db.execute(
                    "SELECT * FROM users WHERE username = ?",
                    (user_identifier,)
                )
            
            row = await cursor.fetchone()
            await cursor.close()
            
            if not row:
                return None
            
            # 解析原始数据
            raw_data = json.loads(row[9]) if row[9] else None
            if raw_data:
                # 标记为来自缓存
                raw_data['fromCache'] = True
                raw_data['dataSource'] = '本地数据库'
                return raw_data
            
            return None
            
        except Exception as e:
            logger.error(f"查询用户数据失败: {e}")
            return None
    
    async def get_statistics(self) -> Dict[str, int]:
        """获取数据库统计信息"""
        try:
            stats = {}
            
            cursor = await self.db.execute("SELECT COUNT(*) FROM users")
            stats['users'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            cursor = await self.db.execute("SELECT COUNT(*) FROM groups")
            stats['groups'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            cursor = await self.db.execute("SELECT COUNT(*) FROM messages")
            stats['messages'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            return stats
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    async def log_query(self, queried_user: str, querier_user_id: int, from_cache: bool = False):
        """
        记录查询日志
        
        Args:
            queried_user: 被查询的用户名/ID
            querier_user_id: 查询者的用户ID
            from_cache: 是否从缓存获取
        """
        try:
            await self.db.execute("""
                INSERT INTO query_logs (queried_user, querier_user_id, from_cache)
                VALUES (?, ?, ?)
            """, (queried_user, querier_user_id, 1 if from_cache else 0))
            await self.db.commit()
        except Exception as e:
            logger.error(f"记录查询日志失败: {e}")
    
    async def log_text_query(self, keyword: str, user_id: int, from_cache: bool = False):
        """记录关键词搜索日志"""
        try:
            await self.db.execute("""
                INSERT INTO text_query_logs (keyword, user_id, from_cache)
                VALUES (?, ?, ?)
            """, (keyword, user_id, 1 if from_cache else 0))
            await self.db.commit()
        except Exception as e:
            logger.error(f"记录关键词搜索日志失败: {e}")
    
    async def get_query_stats(self, period: str = 'day') -> Dict[str, Any]:
        """
        获取查询统计信息
        
        Args:
            period: 统计周期 'day', 'week', 'month', 'year'
        
        Returns:
            统计信息字典
        """
        try:
            # 计算时间范围
            now = datetime.now()
            end_time = None
            if period == 'day':
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = '今日'
            elif period == 'yesterday':
                end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_time = end_time - timedelta(days=1)
                period_name = '昨日'
            elif period == 'week':
                start_time = now - timedelta(days=now.weekday())
                start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = '本周'
            elif period == 'month':
                start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                period_name = '本月'
            elif period == 'year':
                start_time = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                period_name = '今年'
            else:
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = '今日'
            
            # 使用SQLite兼容的时间格式，避免'YYYY-MM-DDTHH'导致比较失败
            start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None
            
            stats = {'period': period_name}
            
            # 查询总次数
            # 用户查询次数
            if end_time_str:
                cursor = await self.db.execute("""
                    SELECT COUNT(*) FROM query_logs 
                    WHERE query_time >= ? AND query_time < ?
                """, (start_time_str, end_time_str))
            else:
                cursor = await self.db.execute("""
                    SELECT COUNT(*) FROM query_logs 
                    WHERE query_time >= ?
                """, (start_time_str,))
            stats['user_queries'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            # 关键词查询次数
            if end_time_str:
                cursor = await self.db.execute("""
                    SELECT COUNT(*) FROM text_query_logs 
                    WHERE query_time >= ? AND query_time < ?
                """, (start_time_str, end_time_str))
            else:
                cursor = await self.db.execute("""
                    SELECT COUNT(*) FROM text_query_logs 
                    WHERE query_time >= ?
                """, (start_time_str,))
            stats['text_queries'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            stats['total_queries'] = stats['user_queries'] + stats['text_queries']
            
            # 活跃用户数（查询的不同用户数）
            # 活跃用户（期间内，用户查询 ∪ 关键词查询）
            if end_time_str:
                cursor = await self.db.execute("""
                    SELECT COUNT(DISTINCT user_id) FROM (
                        SELECT querier_user_id AS user_id FROM query_logs WHERE query_time >= ? AND query_time < ?
                        UNION
                        SELECT user_id AS user_id FROM text_query_logs WHERE query_time >= ? AND query_time < ?
                    )
                """, (start_time_str, end_time_str, start_time_str, end_time_str))
            else:
                cursor = await self.db.execute("""
                    SELECT COUNT(DISTINCT user_id) FROM (
                        SELECT querier_user_id AS user_id FROM query_logs WHERE query_time >= ?
                        UNION
                        SELECT user_id AS user_id FROM text_query_logs WHERE query_time >= ?
                    )
                """, (start_time_str, start_time_str))
            stats['active_users'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            # 新增用户数（首次使用的用户）
            # 新增用户（首次使用机器人发生在期间内，统计两类日志的首次时间）
            if end_time_str:
                cursor = await self.db.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT user_id, MIN(first_time) AS ft FROM (
                            SELECT querier_user_id AS user_id, query_time AS first_time FROM query_logs
                            UNION ALL
                            SELECT user_id AS user_id, query_time AS first_time FROM text_query_logs
                        ) GROUP BY user_id
                    ) WHERE ft >= ? AND ft < ?
                """, (start_time_str, end_time_str))
            else:
                cursor = await self.db.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT user_id, MIN(first_time) AS ft FROM (
                            SELECT querier_user_id AS user_id, query_time AS first_time FROM query_logs
                            UNION ALL
                            SELECT user_id AS user_id, query_time AS first_time FROM text_query_logs
                        ) GROUP BY user_id
                    ) WHERE ft >= ?
                """, (start_time_str,))
            stats['new_users'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            return stats
        except Exception as e:
            logger.error(f"获取查询统计失败: {e}")
            return {
                'period': period_name if 'period_name' in locals() else '未知',
                'total_queries': 0,
                'active_users': 0,
                'new_users': 0
            }

    async def get_recharge_stats(self, period: str = 'day') -> Dict[str, Any]:
        """获取充值统计信息（含昨日）"""
        try:
            now = datetime.now()
            end_time = None
            if period == 'day':
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = '今日'
            elif period == 'yesterday':
                end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_time = end_time - timedelta(days=1)
                period_name = '昨日'
            elif period == 'week':
                start_time = now - timedelta(days=now.weekday())
                start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = '本周'
            elif period == 'month':
                start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                period_name = '本月'
            elif period == 'year':
                start_time = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                period_name = '今年'
            else:
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = '今日'
            
            start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None
            
            # where 子句
            if end_time_str:
                where_time = "completed_at >= ? AND completed_at < ?"
                params = (start_time_str, end_time_str)
            else:
                where_time = "completed_at >= ?"
                params = (start_time_str,)
            
            stats = {'period': period_name}
            
            # 完成订单数
            cursor = await self.db.execute(f"""
                SELECT COUNT(*) FROM recharge_orders 
                WHERE status = 'completed' AND {where_time}
            """, params)
            stats['completed_orders'] = (await cursor.fetchone())[0]
            await cursor.close()
            
            # VIP与普通订单数
            cursor = await self.db.execute(f"""
                SELECT 
                    SUM(CASE WHEN order_type = 'vip' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN order_type != 'vip' THEN 1 ELSE 0 END)
                FROM recharge_orders
                WHERE status = 'completed' AND {where_time}
            """, params)
            row = await cursor.fetchone()
            await cursor.close()
            stats['vip_orders'] = int(row[0] or 0)
            stats['recharge_orders'] = int(row[1] or 0)
            
            # 不同币种金额与积分
            cursor = await self.db.execute(f"""
                SELECT 
                    SUM(CASE WHEN currency = 'USDT' THEN actual_amount ELSE 0 END) AS usdt_amount,
                    SUM(CASE WHEN currency = 'TRX' THEN actual_amount ELSE 0 END) AS trx_amount,
                    SUM(points) AS total_points
                FROM recharge_orders
                WHERE status = 'completed' AND {where_time}
            """, params)
            row = await cursor.fetchone()
            await cursor.close()
            stats['usdt_amount'] = float(row[0] or 0.0)
            stats['trx_amount'] = float(row[1] or 0.0)
            stats['total_points'] = float(row[2] or 0.0)
            
            return stats
        except Exception as e:
            logger.error(f"获取充值统计失败: {e}")
            return {
                'period': '未知',
                'completed_orders': 0,
                'vip_orders': 0,
                'recharge_orders': 0,
                'usdt_amount': 0.0,
                'trx_amount': 0.0,
                'total_points': 0.0,
            }

    async def get_total_bot_users(self) -> int:
        """获取累计使用过机器人的用户数量（用户查询 ∪ 关键词查询）"""
        try:
            cursor = await self.db.execute("""
                SELECT COUNT(DISTINCT user_id) FROM (
                    SELECT querier_user_id AS user_id FROM query_logs
                    UNION
                    SELECT user_id AS user_id FROM text_query_logs
                )
            """)
            val = (await cursor.fetchone())[0]
            await cursor.close()
            return int(val or 0)
        except Exception as e:
            logger.error(f"获取累计机器人用户失败: {e}")
            return 0
    
    # ==================== 余额管理方法 ====================
    
    async def get_balance(self, user_id: int) -> float:
        """获取用户余额"""
        try:
            cursor = await self.db.execute(
                "SELECT balance FROM user_balance WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return float(row[0])
            else:
                # 用户不存在，创建记录
                await self.db.execute("""
                    INSERT INTO user_balance (user_id, balance)
                    VALUES (?, 0.0)
                """, (user_id,))
                await self.db.commit()
                return 0.0
        except Exception as e:
            logger.error(f"获取用户余额失败: {e}")
            return 0.0
    
    async def change_balance(self, user_id: int, amount: float, change_type: str, 
                            description: str = '', operator_id: int = None) -> bool:
        """
        修改用户余额
        
        Args:
            user_id: 用户ID
            amount: 变动金额（正数为增加，负数为减少）
            change_type: 变动类型 (checkin, query, admin_add, admin_deduct, admin_set)
            description: 描述
            operator_id: 操作者ID（管理员操作时使用）
        
        Returns:
            是否成功
        """
        try:
            # 确保用户记录存在
            balance_before = await self.get_balance(user_id)
            
            # 检查余额是否足够（如果是扣款）
            if amount < 0 and balance_before + amount < 0:
                logger.warning(f"用户 {user_id} 余额不足，当前: {balance_before}, 尝试扣除: {abs(amount)}")
                return False
            
            balance_after = balance_before + amount
            
            # 更新余额
            if change_type == 'admin_set':
                # 直接设置余额
                await self.db.execute("""
                    UPDATE user_balance 
                    SET balance = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (amount, user_id))
                balance_after = amount
            else:
                # 增加或减少余额
                if amount > 0:
                    await self.db.execute("""
                        UPDATE user_balance 
                        SET balance = balance + ?,
                            total_earned = total_earned + ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    """, (amount, amount, user_id))
                else:
                    await self.db.execute("""
                        UPDATE user_balance 
                        SET balance = balance + ?,
                            total_spent = total_spent + ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    """, (amount, abs(amount), user_id))
            
            # 记录日志
            await self.db.execute("""
                INSERT INTO balance_logs 
                (user_id, change_amount, balance_before, balance_after, 
                 change_type, description, operator_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, amount, balance_before, balance_after, 
                  change_type, description, operator_id))
            
            await self.db.commit()
            logger.info(f"用户 {user_id} 余额变动: {balance_before} -> {balance_after} ({change_type})")
            return True
            
        except Exception as e:
            logger.error(f"修改用户余额失败: {e}")
            await self.db.rollback()
            return False
    
    async def checkin(self, user_id: int) -> tuple[bool, float, str]:
        """
        用户签到
        
        Returns:
            (是否成功, 奖励金额, 消息)
        """
        try:
            import random
            
            # 获取今天日期
            today = datetime.now().date().isoformat()
            
            # 检查今天是否已签到
            cursor = await self.db.execute("""
                SELECT id FROM checkin_records 
                WHERE user_id = ? AND checkin_date = ?
            """, (user_id, today))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return False, 0, "今天已经签到过了！"
            
            # 获取签到奖励范围
            checkin_min = int(float(await self.get_config('checkin_min', '1')))
            checkin_max = int(float(await self.get_config('checkin_max', '5')))
            
            # 随机整数奖励
            reward = float(random.randint(checkin_min, checkin_max))
            
            # 记录签到
            await self.db.execute("""
                INSERT INTO checkin_records (user_id, checkin_date, reward)
                VALUES (?, ?, ?)
            """, (user_id, today, reward))
            
            # 增加余额
            success = await self.change_balance(
                user_id, reward, 'checkin', 
                f'每日签到奖励 {reward} 积分'
            )
            
            if success:
                return True, reward, f"签到成功！获得 {reward} 积分"
            else:
                await self.db.rollback()
                return False, 0, "签到失败，请稍后重试"
                
        except Exception as e:
            logger.error(f"签到失败: {e}")
            await self.db.rollback()
            return False, 0, "签到失败，请稍后重试"
    
    async def get_checkin_info(self, user_id: int) -> Dict[str, Any]:
        """获取用户签到信息"""
        try:
            # 今天是否已签到
            today = datetime.now().date().isoformat()
            cursor = await self.db.execute("""
                SELECT checkin_time, reward FROM checkin_records 
                WHERE user_id = ? AND checkin_date = ?
            """, (user_id, today))
            row = await cursor.fetchone()
            await cursor.close()
            
            today_checked = row is not None
            today_reward = float(row[1]) if row else 0
            
            # 总签到次数
            cursor = await self.db.execute("""
                SELECT COUNT(*), COALESCE(SUM(reward), 0) 
                FROM checkin_records 
                WHERE user_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            total_days = row[0] if row else 0
            total_rewards = float(row[1]) if row else 0
            
            return {
                'today_checked': today_checked,
                'today_reward': today_reward,
                'total_days': total_days,
                'total_rewards': total_rewards
            }
        except Exception as e:
            logger.error(f"获取签到信息失败: {e}")
            return {
                'today_checked': False,
                'today_reward': 0,
                'total_days': 0,
                'total_rewards': 0
            }
    
    # ==================== 系统配置方法 ====================
    
    async def get_config(self, key: str, default: str = '') -> str:
        """获取系统配置"""
        try:
            cursor = await self.db.execute(
                "SELECT config_value FROM system_config WHERE config_key = ?",
                (key,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            
            return row[0] if row else default
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return default
    
    async def set_config(self, key: str, value: str, description: str = '') -> bool:
        """设置系统配置"""
        try:
            await self.db.execute("""
                INSERT OR REPLACE INTO system_config 
                (config_key, config_value, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, value, description))
            await self.db.commit()
            logger.info(f"配置已更新: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"设置配置失败: {e}")
            return False
    
    # ==================== 隐藏用户管理方法 ====================
    
    async def hide_user(self, user_identifier: str, admin_id: int, reason: str = '') -> bool:
        """
        隐藏用户数据
        
        Args:
            user_identifier: 用户名或用户ID
            admin_id: 管理员ID
            reason: 隐藏原因
        
        Returns:
            是否成功
        """
        try:
            await self.db.execute("""
                INSERT OR REPLACE INTO hidden_users (user_identifier, hidden_by, reason)
                VALUES (?, ?, ?)
            """, (user_identifier.lower(), admin_id, reason))
            await self.db.commit()
            logger.info(f"用户 {user_identifier} 已被隐藏，操作者: {admin_id}")
            return True
        except Exception as e:
            logger.error(f"隐藏用户失败: {e}")
            return False
    
    async def unhide_user(self, user_identifier: str) -> bool:
        """
        取消隐藏用户数据
        
        Args:
            user_identifier: 用户名或用户ID
        
        Returns:
            是否成功
        """
        try:
            await self.db.execute("""
                DELETE FROM hidden_users WHERE user_identifier = ?
            """, (user_identifier.lower(),))
            await self.db.commit()
            logger.info(f"用户 {user_identifier} 已取消隐藏")
            return True
        except Exception as e:
            logger.error(f"取消隐藏用户失败: {e}")
            return False
    
    async def is_user_hidden(self, user_identifier: str) -> bool:
        """
        检查用户是否被隐藏
        
        Args:
            user_identifier: 用户名或用户ID
        
        Returns:
            是否被隐藏
        """
        try:
            cursor = await self.db.execute("""
                SELECT user_identifier FROM hidden_users 
                WHERE user_identifier = ?
            """, (user_identifier.lower(),))
            row = await cursor.fetchone()
            await cursor.close()
            return row is not None
        except Exception as e:
            logger.error(f"检查用户隐藏状态失败: {e}")
            return False
    
    async def get_hidden_users_list(self) -> List[Dict[str, Any]]:
        """获取所有隐藏用户列表"""
        try:
            cursor = await self.db.execute("""
                SELECT user_identifier, hidden_by, hidden_at, reason 
                FROM hidden_users 
                ORDER BY hidden_at DESC
            """)
            rows = await cursor.fetchall()
            await cursor.close()
            
            hidden_users = []
            for row in rows:
                hidden_users.append({
                    'user_identifier': row[0],
                    'hidden_by': row[1],
                    'hidden_at': row[2],
                    'reason': row[3] or '无'
                })
            
            return hidden_users
        except Exception as e:
            logger.error(f"获取隐藏用户列表失败: {e}")
            return []
    
    # ==================== 邀请功能方法 ====================
    
    async def is_existing_user(self, user_id: int) -> bool:
        """
        检查用户是否已存在于数据库（是否是老用户）
        
        Args:
            user_id: 用户ID
        
        Returns:
            True表示是老用户，False表示是新用户
        """
        try:
            # 检查user_balance表中是否已有记录
            cursor = await self.db.execute("""
                SELECT user_id FROM user_balance WHERE user_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            return row is not None
        except Exception as e:
            logger.error(f"检查用户是否存在失败: {e}")
            return False
    
    async def record_invitation(self, inviter_id: int, invitee_id: int, invitee_username: str = '') -> tuple[bool, str]:
        """
        记录邀请关系
        
        Args:
            inviter_id: 邀请者ID
            invitee_id: 被邀请者ID
            invitee_username: 被邀请者用户名
        
        Returns:
            (是否成功, 消息)
        """
        try:
            # 检查被邀请者是否已经被邀请过
            cursor = await self.db.execute("""
                SELECT inviter_id FROM invitations WHERE invitee_id = ?
            """, (invitee_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return False, "您已经通过邀请链接注册过了"
            
            # 不能邀请自己
            if inviter_id == invitee_id:
                return False, "不能使用自己的邀请链接"
            
            # 获取邀请奖励金额
            reward = float(await self.get_config('invite_reward', '1'))
            
            # 记录邀请
            await self.db.execute("""
                INSERT INTO invitations (inviter_id, invitee_id, invitee_username, reward)
                VALUES (?, ?, ?, ?)
            """, (inviter_id, invitee_id, invitee_username, reward))
            
            # 给邀请者增加奖励
            inviter_success = await self.change_balance(
                inviter_id, reward, 'invite',
                f'邀请用户 {invitee_username or invitee_id} 获得奖励'
            )
            
            # 给被邀请者也增加奖励
            invitee_success = await self.change_balance(
                invitee_id, reward, 'invite_bonus',
                f'通过邀请链接注册获得奖励'
            )
            
            if inviter_success and invitee_success:
                await self.db.commit()
                reward_str = f'{int(reward)}' if reward == int(reward) else f'{reward:.2f}'
                logger.info(f"邀请记录成功: {inviter_id} 邀请了 {invitee_id}，双方各获得 {reward} 积分")
                return True, f"邀请成功！您获得了 {reward_str} 积分 奖励"
            else:
                await self.db.rollback()
                return False, "奖励发放失败"
                
        except Exception as e:
            logger.error(f"记录邀请失败: {e}")
            await self.db.rollback()
            return False, "邀请记录失败"
    
    async def get_invitation_stats(self, user_id: int) -> Dict[str, Any]:
        """获取用户邀请统计"""
        try:
            # 邀请总人数
            cursor = await self.db.execute("""
                SELECT COUNT(*), COALESCE(SUM(reward), 0)
                FROM invitations 
                WHERE inviter_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            total_invites = row[0] if row else 0
            total_rewards = float(row[1]) if row else 0
            
            return {
                'total_invites': total_invites,
                'total_rewards': total_rewards
            }
        except Exception as e:
            logger.error(f"获取邀请统计失败: {e}")
            return {
                'total_invites': 0,
                'total_rewards': 0
            }
    
    async def is_invited_user(self, user_id: int) -> bool:
        """检查用户是否已被邀请"""
        try:
            cursor = await self.db.execute("""
                SELECT id FROM invitations WHERE invitee_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            return row is not None
        except Exception as e:
            logger.error(f"检查邀请状态失败: {e}")
            return False
    
    # ==================== 充值功能方法 ====================
    
    async def allocate_amount_identifier(self, base_amount: float, currency: str = 'TRX') -> Optional[float]:
        """
        分配唯一的充值金额标识（随机后缀）
        
        Args:
            base_amount: 基础金额（如100）
            currency: 币种（TRX/USDT）
        
        Returns:
            带标识的金额（如100.12），失败返回None
        """
        try:
            import random
            max_attempts = 100  # 最多尝试100次
            used_suffixes = set()  # 记录已尝试的后缀
            
            for _ in range(max_attempts):
                # 随机生成0.01-0.99之间的标识
                identifier_suffix = random.randint(1, 99)
                
                # 如果已经尝试过这个后缀，跳过
                if identifier_suffix in used_suffixes:
                    continue
                used_suffixes.add(identifier_suffix)
                
                identifier = base_amount + (identifier_suffix / 100.0)
                
                # 检查是否已被使用（区分币种）
                cursor = await self.db.execute("""
                    SELECT id FROM amount_identifiers 
                    WHERE identifier = ? AND currency = ? AND is_used = 0
                """, (identifier, currency))
                row = await cursor.fetchone()
                await cursor.close()
                
                if not row:
                    # 标识未被使用，插入记录
                    await self.db.execute("""
                        INSERT INTO amount_identifiers (identifier, currency, is_used)
                        VALUES (?, ?, 0)
                    """, (identifier, currency))
                    await self.db.commit()
                    logger.info(f"分配金额标识: {identifier} {currency}")
                    return identifier
            
            logger.error(f"无法为金额 {base_amount} {currency} 分配标识，所有标识已被占用")
            return None
            
        except Exception as e:
            logger.error(f"分配金额标识失败: {e}")
            await self.db.rollback()
            return None
    
    async def mark_identifier_used(self, identifier: float, currency: str, order_id: str) -> bool:
        """标记金额标识为已使用"""
        try:
            await self.db.execute("""
                UPDATE amount_identifiers 
                SET is_used = 1, order_id = ?
                WHERE identifier = ? AND currency = ?
            """, (order_id, identifier, currency))
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"标记金额标识失败: {e}")
            return False
    
    async def release_identifier(self, identifier: float, currency: str) -> bool:
        """释放金额标识"""
        try:
            await self.db.execute("""
                UPDATE amount_identifiers 
                SET is_used = 0, order_id = NULL, released_at = CURRENT_TIMESTAMP
                WHERE identifier = ? AND currency = ?
            """, (identifier, currency))
            await self.db.commit()
            logger.info(f"释放金额标识: {identifier} {currency}")
            return True
        except Exception as e:
            logger.error(f"释放金额标识失败: {e}")
            return False
    
    async def create_recharge_order(self, user_id: int, currency: str, amount: float, 
                                   actual_amount: float, wallet_address: str, 
                                   expired_at: str) -> Optional[str]:
        """
        创建充值订单
        
        Args:
            user_id: 用户ID
            currency: 货币类型（USDT/TRX）
            amount: 原始金额
            actual_amount: 实际金额（带标识）
            wallet_address: 充值钱包地址
            expired_at: 过期时间
        
        Returns:
            订单ID，失败返回None
        """
        try:
            import uuid
            import datetime
            
            order_id = f"RO{int(datetime.datetime.now().timestamp())}{user_id}"
            
            await self.db.execute("""
                INSERT INTO recharge_orders 
                (order_id, user_id, currency, amount, actual_amount, status, wallet_address, expired_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (order_id, user_id, currency, amount, actual_amount, wallet_address, expired_at))
            
            # 标记金额标识为已使用
            await self.mark_identifier_used(actual_amount, currency, order_id)
            
            await self.db.commit()
            logger.info(f"创建充值订单: {order_id}, 用户: {user_id}, 金额: {actual_amount} {currency}")
            return order_id
            
        except Exception as e:
            logger.error(f"创建充值订单失败: {e}")
            await self.db.rollback()
            return None
    
    async def get_active_order(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户的活跃订单（pending状态）"""
        try:
            cursor = await self.db.execute("""
                SELECT order_id, currency, amount, actual_amount, status, 
                       wallet_address, created_at, expired_at
                FROM recharge_orders
                WHERE user_id = ? AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    'order_id': row[0],
                    'currency': row[1],
                    'amount': row[2],
                    'actual_amount': row[3],
                    'status': row[4],
                    'wallet_address': row[5],
                    'created_at': row[6],
                    'expired_at': row[7]
                }
            return None
        except Exception as e:
            logger.error(f"获取活跃订单失败: {e}")
            return None
    
    async def update_order_status(self, order_id: str, status: str, tx_hash: str = None) -> bool:
        """更新订单状态"""
        try:
            if tx_hash:
                await self.db.execute("""
                    UPDATE recharge_orders 
                    SET status = ?, tx_hash = ?, updated_at = CURRENT_TIMESTAMP,
                        completed_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END
                    WHERE order_id = ?
                """, (status, tx_hash, status, order_id))
            else:
                await self.db.execute("""
                    UPDATE recharge_orders 
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                """, (status, order_id))
            
            await self.db.commit()
            logger.info(f"订单状态更新: {order_id} -> {status}")
            return True
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
            return False
    
    async def cancel_order(self, order_id: str) -> bool:
        """取消订单并释放金额标识"""
        try:
            # 获取订单信息
            cursor = await self.db.execute("""
                SELECT actual_amount, currency FROM recharge_orders WHERE order_id = ?
            """, (order_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if not row:
                return False
            
            actual_amount, currency = row
            
            # 更新订单状态
            await self.update_order_status(order_id, 'cancelled')
            
            # 释放金额标识
            await self.release_identifier(actual_amount, currency)
            
            logger.info(f"订单已取消: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False
    
    async def expire_old_orders(self) -> int:
        """过期超时的订单"""
        try:
            import datetime
            
            # 查找所有超时的pending订单
            cursor = await self.db.execute("""
                SELECT order_id, actual_amount, currency FROM recharge_orders
                WHERE status = 'pending' AND expired_at < datetime('now')
            """)
            rows = await cursor.fetchall()
            await cursor.close()
            
            expired_count = 0
            for row in rows:
                order_id, actual_amount, currency = row
                
                # 更新订单状态
                await self.update_order_status(order_id, 'expired')
                
                # 释放金额标识
                await self.release_identifier(actual_amount, currency)
                
                expired_count += 1
                logger.info(f"订单已过期: {order_id}")
            
            return expired_count
        except Exception as e:
            logger.error(f"过期订单处理失败: {e}")
            return 0
    
    async def find_order_by_amount(self, actual_amount: float, currency: str) -> Optional[Dict[str, Any]]:
        """根据实际金额和币种查找订单"""
        try:
            cursor = await self.db.execute("""
                SELECT order_id, user_id, currency, amount, status, wallet_address
                FROM recharge_orders
                WHERE actual_amount = ? AND currency = ? AND status = 'pending'
                LIMIT 1
            """, (actual_amount, currency))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    'order_id': row[0],
                    'user_id': row[1],
                    'currency': row[2],
                    'amount': row[3],
                    'status': row[4],
                    'wallet_address': row[5]
                }
            return None
        except Exception as e:
            logger.error(f"查找订单失败: {e}")
            return None
    
    async def complete_recharge_order(self, order_id: str, tx_hash: str, points_awarded: float) -> bool:
        """完成充值订单"""
        try:
            # 获取订单信息
            cursor = await self.db.execute("""
                SELECT user_id, actual_amount, currency FROM recharge_orders WHERE order_id = ?
            """, (order_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if not row:
                return False
            
            user_id, actual_amount, currency = row
            
            # 更新订单状态
            await self.update_order_status(order_id, 'completed', tx_hash)
            
            # 增加用户积分
            await self.change_balance(
                user_id, points_awarded, 'recharge',
                f'充值 {actual_amount} {currency} (订单:{order_id})'
            )
            
            # 释放金额标识
            await self.release_identifier(actual_amount, currency)
            
            logger.info(f"充值订单完成: {order_id}, 用户{user_id}获得{points_awarded}积分")
            return True
        except Exception as e:
            logger.error(f"完成充值订单失败: {e}")
            return False
    
    async def save_block_scan(self, currency: str, block_number: int) -> bool:
        """保存区块扫描记录"""
        try:
            await self.db.execute("""
                INSERT OR REPLACE INTO block_scan_records (currency, block_number)
                VALUES (?, ?)
            """, (currency, block_number))
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"保存区块扫描记录失败: {e}")
            return False
    
    async def get_last_scanned_block(self, currency: str) -> Optional[int]:
        """获取最后扫描的区块号"""
        try:
            cursor = await self.db.execute("""
                SELECT block_number FROM block_scan_records
                WHERE currency = ?
                ORDER BY block_number DESC
                LIMIT 1
            """, (currency,))
            row = await cursor.fetchone()
            await cursor.close()
            
            return row[0] if row else None
        except Exception as e:
            logger.error(f"获取最后扫描区块失败: {e}")
            return None
    
    async def save_text_search_cache(self, keyword: str, total: int, results_json: str) -> bool:
        """保存或更新文本搜索缓存"""
        try:
            await self.db.execute("""
                INSERT OR REPLACE INTO text_search_cache (keyword, total, results_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (keyword, total, results_json))
            await self.db.commit()
            logger.info(f"文本搜索缓存已保存: 关键词={keyword}, 总数={total}")
            return True
        except Exception as e:
            logger.error(f"保存文本搜索缓存失败: {e}")
            return False
    
    async def get_text_search_cache(self, keyword: str) -> Optional[Dict[str, Any]]:
        """获取文本搜索缓存"""
        try:
            cursor = await self.db.execute("""
                SELECT total, results_json, updated_at FROM text_search_cache
                WHERE keyword = ?
            """, (keyword,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    'total': row[0],
                    'results_json': row[1],
                    'updated_at': row[2]
                }
            return None
        except Exception as e:
            logger.error(f"获取文本搜索缓存失败: {e}")
            return None
    
    async def get_text_search_total(self, keyword: str) -> Optional[int]:
        """获取某个关键词的缓存总数"""
        try:
            cursor = await self.db.execute("""
                SELECT total FROM text_search_cache
                WHERE keyword = ?
            """, (keyword,))
            row = await cursor.fetchone()
            await cursor.close()
            
            return row[0] if row else None
        except Exception as e:
            logger.error(f"获取文本搜索总数失败: {e}")
            return None
    
    async def save_related_users_cache(self, user_id: int, total: int, results_json: str) -> bool:
        """保存或更新关联用户缓存"""
        try:
            await self.db.execute("""
                INSERT OR REPLACE INTO related_users_cache (user_id, total, results_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, total, results_json))
            await self.db.commit()
            logger.info(f"关联用户缓存已保存: user_id={user_id}, 总数={total}")
            return True
        except Exception as e:
            logger.error(f"保存关联用户缓存失败: {e}")
            return False
    
    async def get_related_users_cache(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取关联用户缓存"""
        try:
            cursor = await self.db.execute("""
                SELECT total, results_json, updated_at FROM related_users_cache
                WHERE user_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    'total': row[0],
                    'results_json': row[1],
                    'updated_at': row[2]
                }
            return None
        except Exception as e:
            logger.error(f"获取关联用户缓存失败: {e}")
            return None
    
    async def get_related_users_total(self, user_id: int) -> Optional[int]:
        """获取某个用户的关联用户缓存总数"""
        try:
            cursor = await self.db.execute("""
                SELECT total FROM related_users_cache
                WHERE user_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            return row[0] if row else None
        except Exception as e:
            logger.error(f"获取关联用户总数失败: {e}")
            return None
    
    # ==================== VIP相关方法 ====================
    
    async def get_user_vip_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户VIP信息"""
        try:
            cursor = await self.db.execute("""
                SELECT expire_time FROM users_vip
                WHERE user_id = ? AND expire_time > datetime('now')
            """, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    'is_vip': True,
                    'expire_time': row[0]
                }
            return {
                'is_vip': False,
                'expire_time': None
            }
        except Exception as e:
            logger.error(f"获取VIP信息失败: {e}")
            return {
                'is_vip': False,
                'expire_time': None
            }
    
    async def create_vip_order(self, user_id: int, months: int, currency: str, amount: float, points_value: float) -> Optional[str]:
        """创建VIP购买订单（复用充值订单表）"""
        try:
            import uuid
            from datetime import datetime, timedelta
            
            # 生成订单ID
            order_id = f"VIP{uuid.uuid4().hex[:16].upper()}"
            
            # 分配金额标识符（实际支付金额 = 基础金额 + 随机后缀）
            identifier = await self.allocate_amount_identifier(amount, currency)
            if not identifier:
                logger.error("分配金额标识符失败")
                return None
            
            actual_amount = float(identifier)
            
            # 获取钱包地址（统一，支持配置缺省回退）
            wallet_address = await self.get_config('recharge_wallet')
            if not wallet_address:
                wallet_address = getattr(config, 'RECHARGE_WALLET_ADDRESS', '')
            
            # 获取超时时间
            timeout_seconds = int(await self.get_config('recharge_timeout', '1800'))
            expired_at = (datetime.now() + timedelta(seconds=timeout_seconds)).strftime('%Y-%m-%d %H:%M:%S')
            
            # 创建订单，order_type设为'vip'
            await self.db.execute("""
                INSERT INTO recharge_orders (
                    order_id, user_id, currency, base_amount, actual_amount, amount,
                    identifier, points, status, order_type, vip_months, 
                    wallet_address, created_at, expired_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'vip', ?, ?, datetime('now'), ?)
            """, (order_id, user_id, currency, amount, actual_amount, actual_amount,
                  identifier, points_value, months, wallet_address, expired_at))
            
            # 标记标识为已使用
            await self.mark_identifier_used(identifier, currency, order_id)
            
            await self.db.commit()
            
            logger.info(f"VIP订单创建成功: order_id={order_id}, user_id={user_id}, months={months}, currency={currency}")
            return order_id
            
        except Exception as e:
            logger.error(f"创建VIP订单失败: {e}")
            return None
    
    async def activate_vip(self, user_id: int, months: int) -> bool:
        """激活或延长VIP"""
        try:
            from datetime import datetime, timedelta
            
            # 检查当前VIP状态
            vip_info = await self.get_user_vip_info(user_id)
            
            if vip_info['is_vip']:
                # 已是VIP，延长时间
                current_expire = datetime.fromisoformat(vip_info['expire_time'])
                new_expire = current_expire + timedelta(days=30 * months)
            else:
                # 新VIP，从现在开始计算
                new_expire = datetime.now() + timedelta(days=30 * months)
            
            # 更新或插入VIP记录
            await self.db.execute("""
                INSERT OR REPLACE INTO users_vip (user_id, expire_time, updated_at)
                VALUES (?, ?, datetime('now'))
            """, (user_id, new_expire.isoformat()))
            
            await self.db.commit()
            logger.info(f"VIP激活成功: user_id={user_id}, 到期时间={new_expire}")
            return True
            
        except Exception as e:
            logger.error(f"激活VIP失败: {e}")
            return False
    
    async def get_daily_query_usage(self, user_id: int, query_type: str) -> Dict[str, Any]:
        """获取用户今日查询使用情况"""
        try:
            from datetime import date
            today = date.today().isoformat()
            
            cursor = await self.db.execute("""
                SELECT used_count FROM vip_query_usage
                WHERE user_id = ? AND query_type = ? AND usage_date = ?
            """, (user_id, query_type, today))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    'used': row[0],
                    'date': today
                }
            return {
                'used': 0,
                'date': today
            }
        except Exception as e:
            logger.error(f"获取查询使用情况失败: {e}")
            return {
                'used': 0,
                'date': None
            }
    
    async def increment_daily_query_usage(self, user_id: int, query_type: str) -> bool:
        """增加今日查询使用次数"""
        try:
            from datetime import date
            today = date.today().isoformat()
            
            await self.db.execute("""
                INSERT INTO vip_query_usage (user_id, query_type, usage_date, used_count, updated_at)
                VALUES (?, ?, ?, 1, datetime('now'))
                ON CONFLICT(user_id, query_type, usage_date) 
                DO UPDATE SET used_count = used_count + 1, updated_at = datetime('now')
            """, (user_id, query_type, today))
            
            await self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"增加查询使用次数失败: {e}")
            return False
    
    async def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """根据订单ID获取订单信息"""
        try:
            cursor = await self.db.execute("""
                SELECT order_id, user_id, currency, amount, actual_amount, base_amount,
                       identifier, points, status, order_type, vip_months,
                       wallet_address, tx_hash, created_at, expired_at, completed_at
                FROM recharge_orders
                WHERE order_id = ?
            """, (order_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    'order_id': row[0],
                    'user_id': row[1],
                    'currency': row[2],
                    'amount': row[3],
                    'actual_amount': row[4],
                    'base_amount': row[5],
                    'identifier': row[6],
                    'points': row[7],
                    'status': row[8],
                    'order_type': row[9],
                    'vip_months': row[10],
                    'wallet_address': row[11],
                    'tx_hash': row[12],
                    'created_at': row[13],
                    'expired_at': row[14],
                    'completed_at': row[15]
                }
            return None
        except Exception as e:
            logger.error(f"获取订单失败: {e}")
            return None
