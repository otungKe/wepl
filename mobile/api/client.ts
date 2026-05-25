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

API.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const token = await storage.getItem("access");
      if (token) {
        // Stored session has expired — clear it and send to home
        await storage.multiRemove(["access", "refresh", "phone", "name"]);
        router.replace("/");
      }
      // No token means this is an unauthenticated request (login attempt).
      // Let the error propagate so the calling screen can show the message.
    }
    return Promise.reject(error);
  }
);

export default API;
