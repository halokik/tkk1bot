"""
Web管理面板 - 基于Flask的配置管理系统
所有HTML模板内嵌，使用Tailwind CSS v3 黑白配色
"""
import asyncio
import logging
from flask import Flask, request, jsonify, redirect, url_for, session, render_template_string
from functools import wraps
import config
from database import Database

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)
app.secret_key = config.BOT_TOKEN[:32]  # 使用BOT_TOKEN作为密钥

# 数据库实例
db = None

# 配置项定义
CONFIG_ITEMS = {
    'checkin': {
        'title': '签到配置',
        'items': [
            {'key': 'checkin_min', 'label': '签到最小奖励', 'type': 'number', 'unit': '积分', 'min': 0},
            {'key': 'checkin_max', 'label': '签到最大奖励', 'type': 'number', 'unit': '积分', 'min': 0},
        ]
    },
    'consumption': {
        'title': '消费配置',
        'items': [
            {'key': 'query_cost', 'label': '用户查询费用', 'type': 'number', 'unit': '积分/次', 'min': 0, 'step': '0.1'},
            {'key': 'text_search_cost', 'label': '关键词查询费用', 'type': 'number', 'unit': '积分/次', 'min': 0, 'step': '0.1'},
        ]
    },
    'invitation': {
        'title': '邀请配置',
        'items': [
            {'key': 'invite_reward', 'label': '邀请奖励', 'type': 'number', 'unit': '积分/人', 'min': 0, 'step': '0.1'},
        ]
    },
    'recharge': {
        'title': '充值配置',
        'items': [
            {'key': 'recharge_timeout', 'label': '订单超时时间', 'type': 'number', 'unit': '秒', 'min': 300},
            {'key': 'recharge_min_amount', 'label': '最小充值金额', 'type': 'number', 'unit': '', 'min': 0, 'step': '0.1'},
            {'key': 'recharge_wallet', 'label': '充值钱包地址', 'type': 'text', 'placeholder': 'T开头的TRON地址'},
        ]
    },
    'exchange': {
        'title': '汇率配置',
        'items': [
            {'key': 'fixed_rate_usdt_points', 'label': 'USDT汇率', 'type': 'number', 'unit': '积分/USDT', 'min': 0, 'step': '0.01'},
            {'key': 'fixed_rate_trx_points', 'label': 'TRX汇率', 'type': 'number', 'unit': '积分/TRX', 'min': 0, 'step': '0.01'},
            {'key': 'exchange_use_api', 'label': 'API汇率开关', 'type': 'switch', 'help': '开启后使用Binance实时汇率'},
        ]
    },
    'vip': {
        'title': 'VIP配置',
        'items': [
            {'key': 'vip_monthly_price', 'label': 'VIP月价格', 'type': 'number', 'unit': '积分', 'min': 0, 'step': '0.1'},
            {'key': 'vip_monthly_query_limit', 'label': 'VIP每月查询次数', 'type': 'number', 'unit': '次', 'min': 0},
        ]
    },
}


# HTML模板
LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>管理员登录 - Bot配置管理</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-black min-h-screen flex items-center justify-center">
    <div class="bg-white p-8 rounded-lg shadow-2xl w-96 border-2 border-gray-800">
        <h1 class="text-3xl font-bold text-center mb-6 text-black">🔐 管理员登录</h1>
        {% if error %}
        <div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4">
            <p>{{ error }}</p>
        </div>
        {% endif %}
        <form method="POST">
            <div class="mb-6">
                <label class="block text-gray-700 text-sm font-bold mb-2">
                    管理员ID
                </label>
                <input type="text" name="user_id" required
                    class="w-full px-4 py-3 border-2 border-gray-800 rounded-lg focus:outline-none focus:border-gray-600"
                    placeholder="请输入您的Telegram用户ID">
            </div>
            <button type="submit"
                class="w-full bg-black text-white font-bold py-3 px-4 rounded-lg hover:bg-gray-800 transition duration-200">
                登录
            </button>
        </form>
        <div class="mt-6 text-center text-sm text-gray-600">
            <p>仅限管理员访问</p>
            <p class="mt-2">管理员列表：{{ admin_ids }}</p>
        </div>
    </div>
</body>
</html>
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot配置管理系统</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: '#ef4444',
                        accent: '#f97316',
                    }
                }
            }
        }
    </script>
    <style>
        body {
            background: linear-gradient(to bottom right, #0a0a0a, #1a1a1a);
            overflow-x: hidden;
        }
        /* 隐藏滚动条但保持滚动功能 */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        /* 隐藏number输入框的上下箭头 */
        input[type=number]::-webkit-inner-spin-button,
        input[type=number]::-webkit-outer-spin-button {
            -webkit-appearance: none;
            margin: 0;
        }
        input[type=number] {
            -moz-appearance: textfield;
        }
        .glass-card {
            backdrop-filter: blur(10px);
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 34px;
        }
        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #4b5563;
            transition: .4s;
            border-radius: 34px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 26px;
            width: 26px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        input:checked + .slider {
            background-color: #ef4444;
        }
        input:checked + .slider:before {
            transform: translateX(26px);
        }
    </style>
</head>
<body class="min-h-screen text-white">
    <!-- 顶部导航栏 -->
    <header class="sticky top-0 z-50 w-full border-b border-white/10 glass-card">
        <div class="container mx-auto px-4 md:px-6">
            <div class="flex h-16 items-center justify-between">
                <div class="flex items-center space-x-3">
                    <div class="h-10 w-10 rounded-lg bg-red-500/20 flex items-center justify-center">
                        <svg class="h-6 w-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                        </svg>
                    </div>
                    <div>
                        <h1 class="text-xl font-bold">Bot配置管理系统</h1>
                        <p class="text-xs text-gray-400">管理员控制面板</p>
                    </div>
                </div>
                <div class="flex items-center space-x-2 bg-red-500/10 text-red-500 px-4 py-2 rounded-full text-sm font-medium">
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                    </svg>
                    <span>{{ user_id }}</span>
                </div>
            </div>
        </div>
    </header>

    <!-- 统计卡片 -->
    <section class="py-8">
        <div class="container mx-auto px-4 md:px-6">
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8" id="stats-container">
                <div class="glass-card rounded-xl p-6 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                    <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/20 mb-3">
                        <svg class="h-6 w-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
                        </svg>
                    </div>
                    <div class="text-gray-400 text-sm mb-1">总用户数</div>
                    <div class="text-3xl font-bold text-red-500" id="stat-users">0</div>
                </div>
                <div class="glass-card rounded-xl p-6 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                    <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/20 mb-3">
                        <svg class="h-6 w-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                        </svg>
                    </div>
                    <div class="text-gray-400 text-sm mb-1">今日查询</div>
                    <div class="text-3xl font-bold text-red-500" id="stat-queries">0</div>
                </div>
                <div class="glass-card rounded-xl p-6 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                    <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/20 mb-3">
                        <svg class="h-6 w-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path>
                        </svg>
                    </div>
                    <div class="text-gray-400 text-sm mb-1">今日新增</div>
                    <div class="text-3xl font-bold text-red-500" id="stat-new-users">0</div>
                </div>
                <div class="glass-card rounded-xl p-6 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                    <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/20 mb-3">
                        <svg class="h-6 w-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"></path>
                        </svg>
                    </div>
                    <div class="text-gray-400 text-sm mb-1">今日订单</div>
                    <div class="text-3xl font-bold text-red-500" id="stat-orders">0</div>
                </div>
            </div>
        </div>
    </section>

    <!-- 配置面板 -->
    <section class="pb-12">
        <div class="container mx-auto px-4 md:px-6">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {% for category_key, category in config_items.items() %}
                <div class="glass-card rounded-xl p-6 hover:shadow-lg transition-all duration-300">
                    <div class="flex items-center space-x-3 mb-6">
                        <h2 class="text-xl font-bold">{{ category.title }}</h2>
                    </div>
                    <div class="space-y-6">
                        {% for item in category['items'] %}
                        <div class="border-t border-white/10 pt-4 first:border-0 first:pt-0">
                            <label class="block text-sm font-medium mb-3">
                                {{ item.label }}
                                {% if item.unit %}
                                <span class="text-gray-400 font-normal text-xs ml-1">({{ item.unit }})</span>
                                {% endif %}
                            </label>
                        
                        {% if item.type == 'switch' %}
                            <div class="flex items-center justify-between p-3 rounded-lg bg-white/5">
                                <span class="text-sm text-gray-400">{{ item.help | default('') }}</span>
                                <label class="switch">
                                    <input type="checkbox" 
                                        data-key="{{ item.key }}"
                                        class="config-switch"
                                        {% if configs[category_key][item.key] %}checked{% endif %}>
                                    <span class="slider"></span>
                                </label>
                            </div>
                        {% elif item.type == 'number' %}
                            <div class="flex items-center space-x-2">
                                <input type="number" 
                                    data-key="{{ item.key }}"
                                    value="{{ configs[category_key][item.key] }}"
                                    min="{{ item.min | default(0) }}"
                                    step="{{ item.step | default('1') }}"
                                    class="config-input flex-1 px-4 py-3 bg-white/5 border border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/50 focus:border-red-500 transition-all text-white">
                                <button onclick="updateConfig('{{ item.key }}')" 
                                    class="px-6 py-3 bg-red-500 hover:bg-red-600 text-white font-medium rounded-lg transition-all duration-200 shadow-lg hover:shadow-xl">
                                    保存
                                </button>
                            </div>
                        {% elif item.type == 'text' %}
                            <div class="flex items-center space-x-2">
                                <input type="text" 
                                    data-key="{{ item.key }}"
                                    value="{{ configs[category_key][item.key] }}"
                                    placeholder="{{ item.placeholder | default('') }}"
                                    class="config-input flex-1 px-4 py-3 bg-white/5 border border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/50 focus:border-red-500 transition-all font-mono text-sm text-white">
                                <button onclick="updateConfig('{{ item.key }}')" 
                                    class="px-6 py-3 bg-red-500 hover:bg-red-600 text-white font-medium rounded-lg transition-all duration-200 shadow-lg hover:shadow-xl">
                                    保存
                                </button>
                            </div>
                        {% endif %}
                        
                        {% if item.key == 'recharge_timeout' %}
                            <div class="text-xs text-gray-400 mt-2" id="timeout-display"></div>
                        {% endif %}
                        </div>
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}

                <!-- 客服管理 -->
                <div class="glass-card rounded-xl p-6 hover:shadow-lg transition-all duration-300">
                    <div class="flex items-center space-x-3 mb-6">
                        <h2 class="text-xl font-bold">客服管理</h2>
                    </div>
                    <div class="space-y-6">
                        <div>
                            <label class="block text-sm font-medium mb-3">
                                客服用户名 <span class="text-gray-400 font-normal text-xs">(每行一个，支持批量)</span>
                            </label>
                            <textarea id="service-usernames" 
                                class="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/50 focus:border-red-500 transition-all font-mono text-sm text-white"
                                rows="3"
                                placeholder="username1&#10;username2&#10;username3"></textarea>
                            <div class="flex space-x-2 mt-3">
                                <button onclick="addServiceAccounts()" 
                                    class="flex-1 px-6 py-3 bg-red-500 hover:bg-red-600 text-white font-medium rounded-lg transition-all duration-200 shadow-lg hover:shadow-xl">
                                    添加客服
                                </button>
                                <button onclick="clearServiceAccounts()" 
                                    class="px-6 py-3 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-all duration-200 border border-white/10">
                                    清空全部
                                </button>
                            </div>
                        </div>
                        <div class="border-t border-white/10 pt-4">
                            <div class="text-sm font-medium mb-3">当前客服列表：</div>
                            <div id="service-list" class="space-y-2">
                                {% if configs['service_accounts'] %}
                                    {% for account in configs['service_accounts'] %}
                                    <div class="flex items-center space-x-2 px-4 py-2 bg-white/5 rounded-lg border border-white/10 font-mono text-sm">
                                        <svg class="h-4 w-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                                        </svg>
                                        <span>@{{ account }}</span>
                                    </div>
                                    {% endfor %}
                                {% else %}
                                    <div class="text-gray-400 text-sm text-center py-4">暂无客服账号</div>
                                {% endif %}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- 通知提示 -->
    <div id="notification" class="fixed top-20 right-4 hidden z-50">
        <div class="glass-card px-6 py-4 rounded-xl shadow-2xl border border-white/20 min-w-[300px]">
            <div class="flex items-center space-x-3">
                <svg id="notification-icon" class="h-6 w-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <p id="notification-message" class="font-medium"></p>
            </div>
        </div>
    </div>

    <script>
        // 显示通知
        function showNotification(message, isError = false) {
            const notification = document.getElementById('notification');
            const messageEl = document.getElementById('notification-message');
            const iconEl = document.getElementById('notification-icon');
            
            messageEl.textContent = message;
            
            // 更新图标
            if (isError) {
                iconEl.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>';
                iconEl.classList.remove('text-red-500');
                iconEl.classList.add('text-red-400');
            } else {
                iconEl.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>';
                iconEl.classList.add('text-red-500');
                iconEl.classList.remove('text-red-400');
            }
            
            notification.classList.remove('hidden');
            notification.classList.add('animate-pulse');
            
            setTimeout(() => {
                notification.classList.add('hidden');
                notification.classList.remove('animate-pulse');
            }, 3000);
        }

        // 更新配置
        async function updateConfig(key) {
            const input = document.querySelector('[data-key="' + key + '"]');
            const value = input.type === 'checkbox' ? input.checked : input.value;
            
            try {
                const response = await fetch('/api/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({key, value})
                });
                const data = await response.json();
                
                if (data.success) {
                    showNotification('✅ ' + data.message);
                } else {
                    showNotification('❌ ' + data.message, true);
                }
            } catch (error) {
                showNotification('❌ 网络错误', true);
            }
        }

        // 开关变化时自动保存
        document.querySelectorAll('.config-switch').forEach(function(el) {
            el.addEventListener('change', function() {
                updateConfig(el.dataset.key);
            });
        });

        // 添加客服账号
        async function addServiceAccounts() {
            const textarea = document.getElementById('service-usernames');
            const text = textarea.value.trim();
            if (!text) {
                showNotification('❌ 请输入客服用户名', true);
                return;
            }
            
            // 手动分隔，避免正则在部分浏览器/扩展环境下报错
            const separators = new Set([',', '，', '\n', '\r', '\t', ' ']);
            const usernames = [];
            let buf = '';
            for (let i = 0; i < text.length; i++) {
                const ch = text[i];
                if (separators.has(ch)) {
                    if (buf.trim()) usernames.push(buf.trim());
                    buf = '';
                } else {
                    buf += ch;
                }
            }
            if (buf.trim()) usernames.push(buf.trim());
            
            try {
                const response = await fetch('/api/service_accounts', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({usernames})
                });
                const data = await response.json();
                
                if (data.success) {
                    showNotification('✅ ' + data.message);
                    textarea.value = '';
                    updateServiceList(data.accounts);
                } else {
                    showNotification('❌ ' + data.message, true);
                }
            } catch (error) {
                showNotification('❌ 网络错误', true);
            }
        }

        // 清空客服账号
        async function clearServiceAccounts() {
            if (!confirm('确定要清空所有客服账号吗？')) return;
            
            try {
                const response = await fetch('/api/service_accounts', {
                    method: 'DELETE'
                });
                const data = await response.json();
                
                if (data.success) {
                    showNotification('✅ ' + data.message);
                    updateServiceList([]);
                } else {
                    showNotification('❌ ' + data.message, true);
                }
            } catch (error) {
                showNotification('❌ 网络错误', true);
            }
        }

        // 更新客服列表显示
        function updateServiceList(accounts) {
            const listEl = document.getElementById('service-list');
            if (accounts.length === 0) {
                listEl.innerHTML = '<div class="text-gray-400 text-sm text-center py-4">暂无客服账号</div>';
            } else {
                listEl.innerHTML = accounts.map(function(acc) {
                    return '<div class="flex items-center space-x-2 px-4 py-2 bg-white/5 rounded-lg border border-white/10 font-mono text-sm">' +
                        '<svg class="h-4 w-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
                        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>' +
                        '</svg>' +
                        '<span>@' + acc + '</span>' +
                        '</div>';
                }).join('');
            }
        }

        // 加载统计数据
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                if (!response.ok) {
                    console.error('API返回错误:', response.status);
                    return;
                }
                const data = await response.json();
                console.log('统计数据:', data);
                if (data.success && data.stats) {
                    document.getElementById('stat-users').textContent = data.stats.total_users || 0;
                    document.getElementById('stat-queries').textContent = data.stats.today_queries || 0;
                    document.getElementById('stat-new-users').textContent = data.stats.today_new_users || 0;
                    document.getElementById('stat-orders').textContent = data.stats.today_orders || 0;
                } else {
                    console.error('统计数据格式错误:', data);
                }
            } catch (error) {
                console.error('加载统计失败', error);
            }
        }

        // 格式化秒数
        function formatSeconds(seconds) {
            const s = parseInt(seconds);
            const minutes = Math.floor(s / 60);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);
            
            if (days > 0) return days + '天 ' + (hours % 24) + '小时';
            if (hours > 0) return hours + '小时 ' + (minutes % 60) + '分钟';
            if (minutes > 0) return minutes + '分钟';
            return s + '秒';
        }

        // 更新超时时间显示
        function updateTimeoutDisplay() {
            const input = document.querySelector('[data-key="recharge_timeout"]');
            const display = document.getElementById('timeout-display');
            if (input && display) {
                display.textContent = '约 ' + formatSeconds(input.value);
                input.addEventListener('input', function() {
                    display.textContent = '约 ' + formatSeconds(input.value);
                });
            }
        }

        // 页面加载完成后执行
        document.addEventListener('DOMContentLoaded', function() {
            console.log('页面加载完成，开始加载统计数据...');
            loadStats();
            updateTimeoutDisplay();
            setInterval(loadStats, 30000); // 每30秒刷新统计
        });
        
        // 页面加载后立即执行（备用）
        window.addEventListener('load', function() {
            loadStats();
        });
    </script>
</body>
</html>
"""


def login_required(f):
    """登录验证装饰器（已禁用）"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


async def init_db():
    """初始化数据库连接"""
    global db
    db = Database()
    await db.connect()
    logger.info("数据库已连接")


async def get_all_configs():
    """获取所有配置项"""
    configs = {}
    for category, category_data in CONFIG_ITEMS.items():
        configs[category] = {}
        for item in category_data['items']:
            key = item['key']
            # 获取默认值
            default = '0' if item['type'] in ['number', 'switch'] else ''
            value = await db.get_config(key, default)
            
            # 开关类型转换为布尔值
            if item['type'] == 'switch':
                value = value in ['1', 'true', 'True']
            
            configs[category][key] = value
    
    # 获取客服账号列表
    service_accounts = await db.get_service_accounts()
    configs['service_accounts'] = service_accounts
    
    return configs


async def update_config(key: str, value: str, description: str = ''):
    """更新配置项"""
    return await db.set_config(key, value, description)




@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面（已禁用，直接跳转到主页）"""
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    """退出登录（已禁用）"""
    return redirect(url_for('index'))


@app.route('/')
def index():
    """主页面 - 显示所有配置"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    configs = loop.run_until_complete(get_all_configs())
    loop.close()
    
    return render_template_string(INDEX_HTML, 
        config_items=CONFIG_ITEMS, 
        configs=configs,
        user_id='管理员')


@app.route('/api/update', methods=['POST'])
def api_update():
    """API - 更新配置"""
    data = request.get_json()
    key = data.get('key')
    value = data.get('value')
    
    if not key:
        return jsonify({'success': False, 'message': '缺少配置键'})
    
    # 查找配置项信息
    config_item = None
    for category_data in CONFIG_ITEMS.values():
        for item in category_data['items']:
            if item['key'] == key:
                config_item = item
                break
        if config_item:
            break
    
    if not config_item:
        return jsonify({'success': False, 'message': '配置项不存在'})
    
    # 验证数据
    if config_item['type'] == 'number':
        try:
            value = float(value)
            if 'min' in config_item and value < config_item['min']:
                return jsonify({'success': False, 'message': f'值不能小于{config_item["min"]}'})
            value = str(value)
        except ValueError:
            return jsonify({'success': False, 'message': '请输入有效的数字'})
    elif config_item['type'] == 'switch':
        value = '1' if value in ['true', True, '1'] else '0'
    elif config_item['type'] == 'text':
        value = str(value).strip()
        if key == 'recharge_wallet':
            # 验证TRON地址格式
            if value and (not value.startswith('T') or len(value) != 34):
                return jsonify({'success': False, 'message': 'TRON地址格式错误'})
    
    # 更新配置
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(update_config(key, value, config_item['label']))
    loop.close()
    
    if success:
        logger.info(f"管理员更新了配置: {key} = {value}")
        return jsonify({'success': True, 'message': '更新成功'})
    else:
        return jsonify({'success': False, 'message': '更新失败'})


@app.route('/api/service_accounts', methods=['GET', 'POST', 'DELETE'])
def api_service_accounts():
    """API - 管理客服账号"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    if request.method == 'GET':
        # 获取客服列表
        accounts = loop.run_until_complete(db.get_service_accounts())
        loop.close()
        return jsonify({'success': True, 'accounts': accounts})
    
    elif request.method == 'POST':
        # 添加客服账号
        data = request.get_json()
        usernames = data.get('usernames', [])
        
        if not usernames:
            loop.close()
            return jsonify({'success': False, 'message': '请输入客服用户名'})
        
        # 清理用户名（去除@和空格）
        usernames = [u.strip().lstrip('@') for u in usernames if u.strip()]
        
        result = loop.run_until_complete(db.add_service_accounts(usernames, None))
        accounts = loop.run_until_complete(db.get_service_accounts())
        loop.close()
        
        logger.info(f"管理员添加了客服账号: {usernames}")
        return jsonify({
            'success': True, 
            'message': f'添加成功: {result["added"]}个，已存在: {result["skipped"]}个',
            'accounts': accounts
        })
    
    elif request.method == 'DELETE':
        # 清空所有客服账号
        count = loop.run_until_complete(db.clear_service_accounts())
        loop.close()
        
        logger.info(f"管理员清空了客服账号")
        return jsonify({'success': True, 'message': f'已清空 {count} 个客服账号'})


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """API - 获取统计数据"""
    try:
        if db is None:
            logger.error("数据库未初始化")
            return jsonify({'success': False, 'message': '数据库未初始化'})
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 获取基础统计
        stats = loop.run_until_complete(db.get_statistics())
        total_users = loop.run_until_complete(db.get_total_bot_users())
        
        # 获取今日统计
        query_stats = loop.run_until_complete(db.get_query_stats('day'))
        recharge_stats = loop.run_until_complete(db.get_recharge_stats('day'))
        
        loop.close()
        
        result = {
            'success': True,
            'stats': {
                'total_users': total_users,
                'cached_users': stats.get('users', 0),
                'cached_groups': stats.get('groups', 0),
                'cached_messages': stats.get('messages', 0),
                'today_queries': query_stats.get('total_queries', 0),
                'today_new_users': query_stats.get('new_users', 0),
                'today_orders': recharge_stats.get('completed_orders', 0),
            }
        }
        
        logger.info(f"统计数据查询成功: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取统计数据失败: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})


def run_web_admin(host='0.0.0.0', port=5000, debug=False):
    """运行Web管理面板"""
    # 初始化数据库
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    
    logger.info(f"🌐 Web管理面板启动: http://{host}:{port}")
    logger.info(f"👥 管理员ID列表: {config.ADMIN_IDS}")
    
    # 运行Flask应用（关闭调试模式的自动重载）
    app.run(host=host, port=port, debug=debug, use_reloader=False)


def start_web_admin_thread(host='0.0.0.0', port=5000):
    """在后台线程中启动Web管理面板"""
    import threading
    
    def run():
        try:
            run_web_admin(host=host, port=port, debug=False)
        except Exception as e:
            logger.error(f"Web管理面板启动失败: {e}")
    
    thread = threading.Thread(target=run, daemon=True, name="WebAdminThread")
    thread.start()
    logger.info(f"✅ Web管理面板后台线程已启动: http://{host}:{port}")
    return thread


if __name__ == '__main__':
    run_web_admin(debug=True)
