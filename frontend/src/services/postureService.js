import api from "./api";

export const postureService = {
  /**
   * Single-angle posture analysis
   * Sends image file, view angle, and tracking month to backend
   */
  async analyzeSingle(file, angle, monthNumber = 1) {
    const form = new FormData();
    form.append("file", file);
    form.append("angle", angle);
    form.append("month_number", String(monthNumber));

    const { data } = await api.post("/analysis/posture/single", form, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return data;
  },

  /**
   * Multi-angle posture analysis (2-4 photos)
   * Maps angle keys directly as file payload parameters
   */
  async analyzeMulti(photosByAngle, monthNumber = 1) {
    const form = new FormData();
    ["front", "back", "left", "right"].forEach((angle) => {
      if (photosByAngle[angle]) {
        form.append(angle, photosByAngle[angle]);
      }
    });
    form.append("month_number", String(monthNumber));

    const { data } = await api.post("/analysis/posture/multi", form, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return data;
  },

  /**
   * Posture progress comparison between baseline and target month
   */
  async comparePosture({
    photo,
    angle,
    newMonthNumber,
    baselineMonth = 1,
    provider = "auto",
  }) {
    const form = new FormData();
    form.append("new_photo", photo);
    form.append("angle", angle);
    form.append("new_month_number", String(newMonthNumber));
    form.append("baseline_month", String(baselineMonth));
    form.append("preferred_provider", provider);

    const { data } = await api.post("/analysis/posture/compare", form, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return data;
  },
};