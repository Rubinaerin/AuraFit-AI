import axios from "axios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("fitcore_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("fitcore_token");
      window.location.href = "/login";
    }

    const detail = error.response?.data?.detail;
    let message;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail?.message) {
      message = detail.message;
    } else if (Array.isArray(detail) && detail[0]?.msg) {
      message = detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join(" · ");
    } else {
      message = error.message || "Something went wrong. Please try again.";
    }

    return Promise.reject({ ...error, message });
  }
);

export default api;