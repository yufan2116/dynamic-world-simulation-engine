# 浏览器 5 次点击验证（防旧 actions 缓存）

在 DevTools → Network 勾选 **Preserve log**，每次点击叙事选项后记录一行。

## 记录模板

| # | clicked action_id | request body (POST /game/action) | response.parsed_intent | response 中 action ids（前 6 个） |
|---|-------------------|----------------------------------|------------------------|----------------------------------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

## 控制台一键打印（每次点击后粘贴运行）

```javascript
// 在点击选项后、下一条请求返回后执行
const last = performance.getEntriesByType('resource')
  .filter(e => e.name.includes('/game/action'))
  .pop();
console.log('last action URL', last?.name);
```

更可靠：在 `frontend/src/App.tsx` 的 action POST 处临时加：

```javascript
console.log('[ACTION_TRACE]', {
  action_id: payload.action_id,
  intent_payload: payload.intent_payload,
  returned_ids: (data.available_actions?.grouped
    ? Object.values(data.available_actions.grouped).flat()
    : []
  ).map(a => a.id),
  player_knowledge: data.player_knowledge,
});
```

## 通过标准

- 每次 `action_id` 与 Network 请求体一致
- `parsed_intent.parse_source === "selected_action"`（选项点击）
- 连续两次 `returned_ids` 不应完全相同（除非刚 rest 且世界无变化）
- `player_knowledge` 随行动增长（observations / followups / rumors）
