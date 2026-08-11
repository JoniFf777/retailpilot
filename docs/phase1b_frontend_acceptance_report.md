# Phase 1B-Frontend Acceptance Patch

日期：2026-08-05

本补丁只收紧公开契约、推荐交互和测试边界。没有修改 Cart、Order、Payment、Redis、RocketMQ，也没有重构 Graph、RAG、Runtime 或推荐算法。

## 验收结论

- Drawer 首次以 closed 挂载不会抢焦点；打开后焦点进入关闭按钮，Escape/关闭按钮都会恢复触发按钮焦点。
- 对比范围为当前消息内最多 4 个 SKU：主 SKU 与 Alternative SKU 均可加入；超过 4 个会显示“最多比较 4 项”，不会静默移除已有选择。
- OpenAPI 已重新导出并生成 TypeScript：Chat status、ProjectionError code、Catalog sale status 均为 Literal enum，Money amount 仍为 string。
- SSE 只接受合法终态；internal/audit 事件在 reducer 边界被忽略。
- projection error 使用固定中文 UI 文案，不直接展示后端 message。

## Playwright

`npm run e2e:list` 当前列出 7 个场景：纯文本 SSE、Status、recommended 四 SKU 对比、no_match、clarification_required、旧纯文本响应、ActionDrawer。`npm run e2e` 实际运行并通过 7/7。

## 实际验证

- 补丁最小后端契约测试：7 passed。
  命令：`conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest -q -p no:cacheprovider tests\api\test_chat_response.py tests\api\test_openapi_schema.py tests\recommendation\test_public_contracts.py`
- 完整受影响后端回归：36 passed。
  命令：`conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest -q -p no:cacheprovider tests\api\test_chat.py tests\api\test_chat_confirm.py tests\api\test_chat_stream.py tests\api\test_chat_response.py tests\api\test_openapi_schema.py tests\recommendation\test_public_contracts.py`
- 前端既有 Acceptance 记录：11 files / 35 tests passed。
  命令：`npm test`（工作目录：`frontend`，Acceptance 基线执行）
- Closeout 新增 ComparisonDrawer 稳定排序测试：1 file / 4 tests passed；完整重跑后为 11 files / 36 tests passed。
  命令：`npm test -- ComparisonDrawer.test.tsx`；随后 `npm test`（工作目录：`frontend`）
- Playwright：7/7 passed。
  命令：`npm run e2e`（工作目录：`frontend`）
- 其他前端验收命令：`npm run lint`、`npm run typecheck`、`npm run typecheck:e2e`、`npm run build`、`npm run check:budget`、`npm run e2e:list`，均通过。
- `git diff --check`：本次直接执行的 `$LASTEXITCODE=0`，因此检查通过。此前收集记录中的 `Exit code: -1` 是旧打包/收集脚本的证据记录问题，不是 Git whitespace 检查失败。
- 未 stage、未 commit、未触发远程 workflow。

## Closeout

Phase 1B closed。Phase 2 未开始。
