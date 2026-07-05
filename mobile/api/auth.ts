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

// Targeted re-submission — the user tops up ONLY the items the reviewer asked
// for (kyc.resubmission_requested); the rest of their KYC is untouched.
export const resubmitKYC = async (formData: FormData) => {
  const response = await API.post("users/kyc/resubmit/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

// Human labels for the re-submittable item keys the backend may request.
export const KYC_ITEM_LABELS: Record<string, string> = {
  id_front:                "Front of ID",
  id_back:                 "Back of ID",
  selfie:                  "Selfie",
  id_number:               "ID number",
  kra_pin:                 "KRA PIN",
  date_of_birth:           "Date of birth",
  physical_address:        "Physical address",
  county:                  "County",
  occupation:              "Occupation",
  source_of_income:        "Source of income",
  expected_monthly_income: "Income band",
  email:                   "Email address",
};

export type Visibility = "everyone" | "members" | "nobody";

export type PrivacyPrefs = {
  phone_visibility:        Visibility;
  photo_visibility:        Visibility;
  contribution_visibility: Visibility;
  discoverable:            boolean;
  show_online_status:      boolean;
};

export const getPrivacyPrefs = async (): Promise<PrivacyPrefs> => {
  const r = await API.get("users/privacy/");
  return r.data;
};

export const updatePrivacyPrefs = async (patch: Partial<PrivacyPrefs>): Promise<PrivacyPrefs> => {
  const r = await API.patch("users/privacy/", patch);
  return r.data;
};
