"""
TG用户查询 Web界面
简约优雅的黑白设计
"""
from flask import Flask, render_template_string, request, jsonify
import aiohttp
import asyncio
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = Flask(__name__)

# API配置
API_URL = os.getenv('QUERY_API_URL', 'http://95.211.190.114')
API_KEY = os.getenv('QUERY_API_KEY', '5e985753daea28d16d94f6c98fd76d53b7340baf9dbe8cfd454b778927814b57')

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TG用户查询</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'SF Pro Display', 
                         'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 900px;
            width: 100%;
            padding: 40px;
            animation: slideIn 0.5s ease-out;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        h1 {
            text-align: center;
            color: #2d3748;
            font-size: 32px;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .subtitle {
            text-align: center;
            color: #718096;
            font-size: 14px;
            margin-bottom: 40px;
        }

        .search-box {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
        }

        input[type="text"] {
            flex: 1;
            padding: 15px 20px;
            font-size: 16px;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            outline: none;
            transition: all 0.3s;
            color: #2d3748;
        }

        input[type="text"]:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        button {
            padding: 15px 40px;
            font-size: 16px;
            font-weight: 600;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s;
            white-space: nowrap;
        }

        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }

        button:active {
            transform: translateY(0);
        }

        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #718096;
            display: none;
        }

        .spinner {
            border: 3px solid #e2e8f0;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .result {
            display: none;
            animation: fadeIn 0.5s;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        .user-card {
            background: #f7fafc;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }

        .user-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e2e8f0;
        }

        .user-avatar {
            width: 60px;
            height: 60px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 24px;
            font-weight: bold;
        }

        .user-info h2 {
            color: #2d3748;
            font-size: 22px;
            margin-bottom: 5px;
        }

        .user-info p {
            color: #718096;
            font-size: 14px;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .stat-item {
            background: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }

        .stat-value {
            font-size: 28px;
            font-weight: 700;
            color: #667eea;
            margin-bottom: 5px;
        }

        .stat-label {
            color: #718096;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .section {
            margin-top: 25px;
        }

        .section-title {
            color: #2d3748;
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .group-list {
            max-height: 400px;
            overflow-y: auto;
        }

        .group-item {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            transition: all 0.2s;
        }

        .group-item:hover {
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transform: translateX(5px);
        }

        .group-item a {
            text-decoration: none;
            color: inherit;
            transition: color 0.2s;
        }

        .group-item a:hover .group-name {
            color: #667eea;
        }

        .group-name {
            color: #2d3748;
            font-weight: 500;
        }

        .group-username {
            color: #667eea;
            font-size: 13px;
            margin-top: 3px;
        }

        .group-count {
            background: #667eea;
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }

        .error {
            background: #fff5f5;
            border-left: 4px solid #fc8181;
            padding: 20px;
            border-radius: 8px;
            color: #c53030;
            display: none;
        }

        .bio {
            background: white;
            padding: 15px;
            border-radius: 8px;
            color: #4a5568;
            line-height: 1.6;
            font-style: italic;
        }

        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
        }

        .info-item {
            background: white;
            padding: 12px 15px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .info-label {
            color: #718096;
            font-size: 13px;
        }

        .info-value {
            color: #2d3748;
            font-weight: 600;
            font-size: 14px;
        }

        /* 滚动条样式 */
        .group-list::-webkit-scrollbar {
            width: 6px;
        }

        .group-list::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }

        .group-list::-webkit-scrollbar-thumb {
            background: #667eea;
            border-radius: 10px;
        }

        @media (max-width: 768px) {
            .container {
                padding: 25px;
            }

            h1 {
                font-size: 24px;
            }

            .search-box {
                flex-direction: column;
            }

            button {
                width: 100%;
            }

            .stats {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 TG用户查询</h1>
        <p class="subtitle">输入 Telegram 用户名或 ID 查询详细信息</p>

        <div class="search-box">
            <input type="text" id="searchInput" placeholder="输入用户名 (如: username) 或用户ID (如: 123456789)" 
                   onkeypress="if(event.key==='Enter') searchUser()">
            <button onclick="searchUser()" id="searchBtn">查询</button>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>正在查询中，请稍候...</p>
        </div>

        <div class="error" id="error"></div>

        <div class="result" id="result"></div>
    </div>

    <script>
        async function searchUser() {
            const input = document.getElementById('searchInput').value.trim();
            if (!input) {
                showError('请输入用户名或用户ID');
                return;
            }

            // 移除 @ 符号
            const user = input.replace('@', '');

            // 显示加载状态
            document.getElementById('loading').style.display = 'block';
            document.getElementById('result').style.display = 'none';
            document.getElementById('error').style.display = 'none';
            document.getElementById('searchBtn').disabled = true;

            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ user: user })
                });

                const data = await response.json();

                // 调试：在控制台打印API返回数据
                console.log('API返回数据:', data);

                if (data.success) {
                    displayResult(data.data);
                } else {
                    showError(data.error || '查询失败，请重试');
                }
            } catch (error) {
                showError('网络错误: ' + error.message);
            } finally {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('searchBtn').disabled = false;
            }
        }

        function escapeHtml(text) {
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return String(text).replace(/[&<>"']/g, m => map[m]);
        }

        function displayResult(data) {
            const basicInfo = data.basicInfo || {};
            const firstName = escapeHtml(basicInfo.firstName || '未知');
            const lastName = escapeHtml(basicInfo.lastName || '');
            const fullName = (firstName + ' ' + lastName).trim();
            const username = escapeHtml(basicInfo.username || '无');
            const userId = escapeHtml(basicInfo.id || data.userId || '无');
            const phone = escapeHtml(basicInfo.phone || '未公开');
            const bio = escapeHtml(basicInfo.bio || '该用户未设置个人简介');
            
            const messageCount = data.messageCount || 0;
            const groupsCount = data.groupsCount || 0;
            const groups = data.groups || [];

            let html = `
                <div class="user-card">
                    <div class="user-header">
                        <div class="user-avatar">${firstName.charAt(0).toUpperCase()}</div>
                        <div class="user-info">
                            <h2>${fullName}</h2>
                            <p>@${username} · ID: ${userId}</p>
                        </div>
                    </div>

                    <div class="stats">
                        <div class="stat-item">
                            <div class="stat-value">${messageCount.toLocaleString()}</div>
                            <div class="stat-label">消息数量</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">${groupsCount.toLocaleString()}</div>
                            <div class="stat-label">群组数量</div>
                        </div>
                    </div>

                    <div class="info-grid">
                        <div class="info-item">
                            <span class="info-label">用户名</span>
                            <span class="info-value">@${username}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">用户ID</span>
                            <span class="info-value">${userId}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">电话</span>
                            <span class="info-value">${phone}</span>
                        </div>
                    </div>

                    <div class="section">
                        <div class="section-title">📝 个人简介</div>
                        <div class="bio">${bio}</div>
                    </div>
                </div>
            `;

            // 显示消息列表
            const messages = data.messages || [];
            if (messages.length > 0) {
                html += `
                    <div class="section">
                        <div class="section-title">💬 发言记录 (前100条)</div>
                        <div class="group-list">
                `;

                messages.slice(0, 100).forEach((msg, index) => {
                    const text = msg.text || '';
                    const mediaCode = msg.mediaCode;
                    const mediaName = msg.mediaName || '';
                    const link = msg.link || '';
                    const chat = msg.chat || {};
                    const chatTitle = escapeHtml(chat.title || '未知群组');
                    const date = msg.date ? new Date(msg.date * 1000).toLocaleString('zh-CN') : '未知时间';
                    
                    // 处理消息文本
                    let displayText = text;
                    if (!text || text.trim() === '') {
                        // 显示媒体类型
                        if (mediaName) {
                            displayText = `[${mediaName}]`;
                        } else if (mediaCode) {
                            const mediaTypes = {
                                1: '[图片]',
                                2: '[视频]',
                                3: '[语音]',
                                4: '[文件]',
                                5: '[贴纸]',
                                8: '[GIF]'
                            };
                            displayText = mediaTypes[mediaCode] || '[媒体消息]';
                        } else {
                            displayText = '[媒体消息]';
                        }
                    }
                    
                    // 限制文本长度
                    if (displayText.length > 80) {
                        displayText = displayText.substring(0, 80) + '...';
                    }
                    
                    displayText = escapeHtml(displayText);

                    html += `
                        <div class="group-item" style="flex-direction: column; align-items: flex-start; gap: 8px;">
                            ${link ? `<a href="${link}" target="_blank" style="text-decoration: none; color: inherit; width: 100%;">` : ''}
                            <div style="width: 100%;">
                                <div class="group-name">${displayText}</div>
                                <div class="group-username">📍 ${chatTitle} · 🕒 ${date}</div>
                            </div>
                            ${link ? `</a>` : ''}
                        </div>
                    `;
                });

                html += `
                        </div>
                    </div>
                `;
            }

            // 显示群组列表
            if (groups.length > 0) {
                html += `
                    <div class="section">
                        <div class="section-title">👥 加入的群组 (${groupsCount})</div>
                        <div class="group-list">
                `;

                groups.forEach(group => {
                    // 正确的数据结构：群组信息在 chat 对象中
                    const chat = group.chat || {};
                    const groupName = escapeHtml(chat.title || '未命名群组');
                    const groupUsername = chat.username ? `@${escapeHtml(chat.username)}` : '私有群组';
                    const chatId = chat.id || '';
                    const msgCount = group.messageCount || 0;

                    // 构建群组链接
                    let groupLink = '';
                    if (chat.username) {
                        groupLink = `https://t.me/${chat.username}`;
                    }

                    html += `
                        <div class="group-item">
                            <div>
                                ${groupLink ? `<a href="${groupLink}" target="_blank" style="text-decoration: none; color: inherit;">` : ''}
                                <div class="group-name">${groupName}</div>
                                ${groupLink ? `</a>` : ''}
                                <div class="group-username">${groupUsername}${chatId && !chat.username ? ` · ID: ${chatId}` : ''}</div>
                            </div>
                            <div class="group-count">${msgCount} 条消息</div>
                        </div>
                    `;
                });

                html += `
                        </div>
                    </div>
                `;
            }

            document.getElementById('result').innerHTML = html;
            document.getElementById('result').style.display = 'block';
        }

        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = '❌ ' + message;
            errorDiv.style.display = 'block';
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 5000);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """首页"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/query', methods=['POST'])
def query_user():
    """查询用户API"""
    try:
        data = request.get_json()
        user = data.get('user', '').strip()
        
        if not user:
            return jsonify({'success': False, 'error': '请输入用户名或用户ID'})
        
        # 调用查询API
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(call_query_api(user))
        loop.close()
        
        if result:
            return jsonify({'success': True, 'data': result})
        else:
            return jsonify({'success': False, 'error': '查询失败，未找到用户或API错误'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

async def call_query_api(user):
    """调用外部查询API"""
    url = f"{API_URL}/api/query"
    headers = {'x-api-key': API_KEY}
    params = {'user': user}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('success'):
                        return result.get('data')
                return None
        except Exception as e:
            print(f"API调用错误: {e}")
            return None

if __name__ == '__main__':
    if not API_KEY:
        print("⚠️  警告: 未设置 QUERY_API_KEY，请在 .env 文件中配置")
        print("提示: 复制 .env 文件并设置 QUERY_API_KEY=your_api_key")
    
    print("=" * 50)
    print("🚀 TG用户查询 Web界面已启动")
    print(f"📍 访问地址: http://localhost:5001")
    print(f"🔗 API地址: {API_URL}")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5001, debug=True)

