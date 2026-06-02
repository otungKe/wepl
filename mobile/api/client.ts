import axios from "axios";
import { router } from "expo-router";
import { API_BASE_URL } from "../constants/config";
import * as storage from "../utils/secureStorage";

const API = axios.create({
  baseURL: API_BASE_URL,
});

API.interceptors.request.use(
  async (config) => {
    const token = await storage.getItem("access");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Queue of callers waiting for a token refresh to complete.
let isRefreshing = false;
let failedQueue: { resolve: (token: string) => void; reject: (err: unknown) => void }[] = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)));
  failedQueue = [];
}

API.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status !== 401) return Promise.reject(error);

    // No stored access token → this is a login/OTP call, let it fail normally.
    const accessToken = await storage.getItem("access");
    if (!accessToken) return Promise.reject(error);

    // Already retried this request — avoid infinite loop.
    if (originalRequest._retry) {
      await storage.multiRemove(["access", "refresh", "phone", "name"]);
      router.replace("/");
      return Promise.reject(error);
    }

    if (isRefreshing) {
      // Another request is already refreshing; queue this one.
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return API(originalRequest);
      });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    const refresh = await storage.getItem("refresh");
    if (!refresh) {
      isRefreshing = false;
      await storage.multiRemove(["access", "refresh", "phone", "name"]);
      router.replace("/");
      return Promise.reject(error);
    }

    try {
      const { data } = await axios.post(`${API_BASE_URL}users/token/refresh/`, { refresh });
      await storage.setItem("access", data.access);
      if (data.refresh) await storage.setItem("refresh", data.refresh);
      processQueue(null, data.access);
      originalRequest.headers.Authorization = `Bearer ${data.access}`;
      return API(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      await storage.multiRemove(["access", "refresh", "phone", "name"]);
      router.replace("/");
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default API;
