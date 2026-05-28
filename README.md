# Dynamic World Simulation Engine

**确定性世界模拟器 + LLM 叙事层** — MVP 剧本「失踪商人的调查」。

世界状态由后端规则引擎确定性维护；LLM 仅负责叙事文本生成（及可选的复杂意图解析），**不得编造**未发生的新地点、NPC 或剧情。

## 架构

```
玩家输入 → 意图解析 → D20 规则引擎 → 世界模拟 → 事件/NPC记忆持久化 → LLM叙事 → 行动选项
```

## 项目结构

```
Dynamic World Simulation Engine/
├── backend/
│   ├── main.py                 # FastAPI 接口
│   ├── requirements.txt
│   ├── save_game.db            # 运行后自动生成
│   ├── engine/
│   │   ├── game_loop.py
│   │   ├── rule_engine.py
│   │   ├── world_state.py
│   │   ├── world_simulator.py
│   │   ├── event_system.py
│   │   ├── npc_memory.py
│   │   ├── narrative_engine.py
│   │   ├── option_generator.py
│   │   └── intent_parser.py
│   ├── storage/db.py
│   └── data/*.json
└── frontend/
    └── src/
        ├── App.tsx
        ├── api.ts
        ├── types.ts
        └── components/
```

## 环境要求

- Python 3.10+
- Node.js 18+

## 后端安装与运行

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
copy .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（可选；无密钥时使用确定性 fallback 叙事）
```

`.env` 示例（**DeepSeek V4**，已提供 `backend/.env` 模板）：

```env
DEEPSEEK_API_KEY=sk-你的密钥
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
```

也可使用 `deepseek-v4-pro`（更强、更慢）。复制 `backend/.env.example` 或编辑已有 `backend/.env` 填入 Key 即可。

> **图像生成**：DeepSeek 不提供 DALL·E 类接口。仅需叙事时可只配 `DEEPSEEK_API_KEY`；需要肖像/场景图时另设 `IMAGE_API_KEY` 指向 OpenAI。

启动：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/game/start` | 初始化新游戏 |
| POST | `/game/action` | `{ "player_input": "..." }` |
| GET | `/game/state` | 世界状态、NPC 记忆、事件日志 |
| GET | `/health` | 健康检查 |

## 前端安装与运行

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。Vite 已将 `/game` 代理到 `http://127.0.0.1:8000`。

可选：创建 `frontend/.env` 指定 API 地址：

```env
VITE_API_URL=http://127.0.0.1:8000
```

## 游戏说明（MVP 剧本）

**地点**：村口、酒馆、仓库、森林小路  

**NPC**：
- 托马斯（村口，怀疑）
- 米拉、艾琳娜（酒馆）
- 瓦里克（森林小路，需调查后出现）

**建议流程**：
1. 在村口与托马斯交谈
2. 前往酒馆询问米拉与艾琳娜
3. 搜查仓库获取脚印线索
4. 沿森林小路追踪并应对瓦里克

## 核心铁律

1. 世界状态 **仅** 由 `world_simulator` + `rule_engine` 修改
2. LLM 叙事提示词禁止杜撰；无 API Key 时使用 `_fallback_narrative`
3. 每回合事件写入 SQLite `events` 表
4. NPC 记忆持久化于 `npc_memories` 表

## AI 图像生成

需配置 `OPENAI_API_KEY`，并确保账户支持 Images API（默认模型 `dall-e-3`）。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/game/generate-portrait` | `{ "description", "style" }` → `{ "url" }`，缓存至 `images` 表 |
| POST | `/game/generate-background` | `{ "location_description", "style", "location_key?" }` |

**风格**：`medieval fantasy` | `xianxia` | `cyberpunk`（亦可在 `data/world_template.json` 扩展）。

所有提示词末尾自动追加世界模板的 `style_description`。

- 新游戏 / 角色创建：`start` 响应含 `portrait_url`、当前地点 `background_url`
- 地点变更：`action` 响应更新 `background_url`（优先读缓存）
- NPC 头像：交谈或到达新地点时懒加载，写入 `npc_portraits`

环境变量：`IMAGE_MODEL`、`IMAGE_STYLE`（见 `.env.example`）。

## 开发说明

- 单会话：MVP 仅支持一个存档槽（`game_state.id = 1`）
- 简单意图走关键词；长句/复杂句可调用 LLM 解析（需 API Key）
- 掷骰：1d20 + D&D 5e 属性调整值 vs DC，含大成功(20)/大失败(1)

## License

MIT（示例项目）
