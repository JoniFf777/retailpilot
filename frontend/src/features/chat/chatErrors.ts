import { ApiError } from "../../api/errors";

export function chatErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "暂时无法连接 ShopMind，请检查后端服务后重试。";
  }
  switch (error.status) {
    case 400:
      return "消息格式不符合要求，请修改后重试。";
    case 401:
      return "当前会话需要通过可信入口完成身份验证。";
    case 403:
      return "当前身份无权访问这段会话。";
    case 409:
      return "请求正在处理或已存在结果，请稍后查看并重试。";
    case 429:
      return "当前运行较多，请稍后再试。";
    case 503:
      return "ShopMind 服务暂时不可用，请稍后再试。";
    default:
      return "ShopMind 暂时无法完成这次请求，请稍后重试。";
  }
}
