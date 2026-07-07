import api from "./api";

export const postureService = {
  async analyzeSingle(file, angle) {
    const form = new FormData();
    form.append("file", file);
    form.append("angle", angle);

    const { data } = await api.post("/analysis/posture/single", form);
    return data;
  },

  async analyzeMulti(photosByAngle) {
    const form = new FormData();
    ["front", "back", "left", "right"].forEach((angle) => {
      if (photosByAngle[angle]) {
        form.append(angle, photosByAngle[angle]);
      }
    });

    const { data } = await api.post("/analysis/posture/multi", form);
    return data;
  },

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

    const { data } = await api.post("/analysis/posture/compare", form);
    return data;
  },
};