import api from "./api";

export const workoutService = {
  /**
   * AI Antrenman programı oluşturma isteği fırlatır.
   * @param {object} options - Gün sayısı, hafta sayısı ve ekipman listesi
   */
  async generatePlan(options) {
    const { data } = await api.post("/workout/generate", options);
    return data;
  },
};