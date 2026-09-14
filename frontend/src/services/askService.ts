import { apiRequest } from "../lib/api";
import type {
  AskQuestionRequest,
  AskQuestionResponse,
} from "../types/api";

export const askService = {
  ask(
    request: AskQuestionRequest,
    signal?: AbortSignal,
  ): Promise<AskQuestionResponse> {
    return apiRequest<AskQuestionResponse>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    });
  },
};

