# TG查询机器人 API 接口文档

## 📌 基础信息

**API 基础 URL**: `http://95.211.190.114`

**认证方式**: 请求头添加 `x-api-key`

**超时时间**: 300秒（5分钟）

---

## 🔍 API 接口列表

### 1. 用户查询接口

**接口地址**: `/api/query`

**请求方式**: `GET`

**请求参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| user | string | 是 | 用户ID或用户名 |

**请求头**:
```
x-api-key: YOUR_API_KEY
```

**请求示例**:
```bash
GET /api/query?user=123456789
Headers:
  x-api-key: YOUR_API_KEY
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "userId": "123456789",
    "basicInfo": {
      "id": 123456789,
      "username": "example_user",
      "firstName": "John",
      "lastName": "Doe",
      "phone": "+1234567890",
      "bio": "用户简介"
    },
    "messageCount": 1500,
    "groupsCount": 25,
    "groups": [
      {
        "id": 987654321,
        "title": "群组名称",
        "username": "groupname",
        "messageCount": 100
      }
    ],
    "commonGroupsStat": [
      {
        "sharedId": 111111111,
        "sharedCount": 5
      }
    ],
    "commonGroupsStatCount": 10
  }
}
```

**错误响应**:
```json
{
  "success": false,
  "error": "用户不存在"
}
```

---

### 2. 关键词搜索接口

**接口地址**: `/api/text`

**请求方式**: `GET`

**请求参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| text | string | 是 | 搜索关键词 |

**请求头**:
```
x-api-key: YOUR_API_KEY
```

**请求示例**:
```bash
GET /api/text?text=关键词
Headers:
  x-api-key: YOUR_API_KEY
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "total": 100,
    "results": [
      {
        "userId": "123456789",
        "username": "example_user",
        "firstName": "John",
        "messageCount": 50,
        "groupsCount": 10
      }
    ]
  }
}
```

---

## 📊 数据结构说明

### 用户基本信息 (BasicInfo)
```typescript
interface BasicInfo {
  id: number;              // 用户ID
  username?: string;       // 用户名（可选）
  firstName?: string;      // 名字
  lastName?: string;       // 姓氏
  phone?: string;          // 电话号码
  bio?: string;            // 个人简介
}
```

### 群组信息 (Group)
```typescript
interface Group {
  id: number;              // 群组ID
  title: string;           // 群组标题
  username?: string;       // 群组用户名
  messageCount: number;    // 消息数量
}
```

### 关联用户统计 (CommonGroupsStat)
```typescript
interface CommonGroupsStat {
  sharedId: number;        // 关联用户ID
  sharedCount: number;     // 共同群组数量
}
```

---

## 🔐 认证说明

所有API请求都需要在请求头中添加API密钥：

```http
x-api-key: YOUR_API_KEY
```

**获取API密钥**: 请联系管理员获取

---

## ⚠️ 错误码说明

| HTTP状态码 | 说明 |
|-----------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未授权（API密钥错误） |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 504 | 请求超时 |

---

## 📝 使用示例

### Python 示例

```python
import aiohttp
import asyncio

API_URL = "http://95.211.190.114"
API_KEY = "YOUR_API_KEY"

async def query_user(user_id):
    """查询用户信息"""
    url = f"{API_URL}/api/query"
    headers = {'x-api-key': API_KEY}
    params = {'user': user_id}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"错误: {response.status}")
                return None

async def search_text(keyword):
    """搜索关键词"""
    url = f"{API_URL}/api/text"
    headers = {'x-api-key': API_KEY}
    params = {'text': keyword}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"错误: {response.status}")
                return None

# 使用示例
async def main():
    # 查询用户
    result = await query_user("123456789")
    print(result)
    
    # 搜索关键词
    result = await search_text("关键词")
    print(result)

asyncio.run(main())
```

### cURL 示例

```bash
# 查询用户
curl -X GET "http://95.211.190.114/api/query?user=123456789" \
  -H "x-api-key: YOUR_API_KEY"

# 搜索关键词
curl -X GET "http://95.211.190.114/api/text?text=关键词" \
  -H "x-api-key: YOUR_API_KEY"
```

---

## 💡 注意事项

1. **超时时间**: API请求超时时间为5分钟，请做好超时处理
2. **频率限制**: 建议使用数据库缓存减少API调用
3. **数据缓存**: 建议缓存查询结果，避免重复请求
4. **错误处理**: 请妥善处理API返回的错误信息
5. **用户名转ID**: 建议先用Telegram API将用户名转为ID再查询，提高成功率

---

## 📞 技术支持

如有问题，请联系管理员。

**最后更新**: 2025-10-28

