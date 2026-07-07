import api from "./api";

export const chatService = {
  async sendMessage(payload) {
    const { data } = await api.post("/chat/message", payload);
    return data;
  },
};