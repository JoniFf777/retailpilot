import type { RecommendationContextView } from "../../api/contracts";
import { RecommendationPanel } from "../recommendation/RecommendationPanel";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "./chatTypes";

export function AssistantMessage({ message, onFillPrompt, onSelectSku }: { message: ChatMessage; onFillPrompt: (prompt: string) => void; onSelectSku?: (skuId: string, context: RecommendationContextView) => void }) {
  return <div className="assistant-message">
    <MessageBubble message={message} />
    {message.response && <RecommendationPanel recommendation={message.response.recommendation} recommendationContext={message.response.recommendation_context} projectionError={message.response.projection_error} onFillPrompt={onFillPrompt} onSelectSku={onSelectSku} />}
  </div>;
}
