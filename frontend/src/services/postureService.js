import api from "./api";

export const postureService = {
  // Tekli fotoğraf analizi - "file" ve "angle" parametreleri birebir eşleşmeli
  async analyzeSingle(file, angle) {
    const form = new FormData();
    form.append("file", file); // FastAPI backend: file: UploadFile
    form.append("angle", angle); // FastAPI backend: angle: str

    const { data } = await api.post("/analysis/posture/single", form, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return data;
  },

  // Çoklu fotoğraf analizi - Açı isimleri ("front", "back" vb.) dosya anahtarı (key) olmalı
  async analyzeMulti(photosByAngle) {
    const form = new FormData();
    ["front", "back", "left", "right"].forEach((angle) => {
      if (photosByAngle[angle]) {
        form.append(angle, photosByAngle[angle]); // FastAPI backend: front: Optional[UploadFile] vb.
      }
    });

    const { data } = await api.post("/analysis/posture/multi", form, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return data;
  },

  // Gelişim karşılaştırma analizi
  async comparePosture({
    photo,
    angle,
    newMonthNumber,
    baselineMonth = 1,
    provider = "auto",
  }) {
    const form = new FormData();
    form.append("new_photo", photo); // FastAPI backend: new_photo: UploadFile
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