import API from "./client";

export const requestOTP = async (phone_number: string) => {
  const response = await API.post("users/otp/request/", { phone_number });
  return response.data;
};

export const verifyOTP = async (phone_number: string, otp: string) => {
  const response = await API.post("users/otp/verify/", { phone_number, otp });
  return response.data;
};

export const setPIN = async (pin: string) => {
  const response = await API.post("users/pin/set/", { pin });
  return response.data;
};

export const resetPIN = async (pin: string) => {
  const response = await API.post("users/pin/reset/", { pin });
  return response.data;
};

export const loginWithPIN = async (phone_number: string, pin: string) => {
  const response = await API.post("users/pin/login/", { phone_number, pin });
  return response.data;
};

export const getProfile = async () => {
  const response = await API.get("users/profile/");
  return response.data;
};

export const updateProfile = async (data: { name?: string; bio?: string }) => {
  const response = await API.patch("users/profile/", data);
  return response.data;
};

export const getKYCStatus = async () => {
  const response = await API.get("users/kyc/");
  return response.data;
};

export const submitKYC = async (formData: FormData) => {
  const response = await API.post("users/kyc/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};
