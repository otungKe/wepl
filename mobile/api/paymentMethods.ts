import API from "./client";

export type PaymentKind = "mpesa" | "card" | "bank";

export type PaymentMethod = {
  id: number;
  kind: PaymentKind;
  kind_label: string;
  label: string;
  is_default: boolean;
  status: "active" | "unavailable";
  display: string;
  mpesa_phone: string;
  card_brand: string;
  card_last4: string;
  card_exp: string;
  bank_name: string;
  bank_account_last4: string;
  created_at: string;
};

export const getPaymentMethods = async (): Promise<PaymentMethod[]> => {
  const r = await API.get("users/payment-methods/");
  return r.data?.results ?? r.data;
};

/** Link an M-Pesa number. Card/bank kinds return 501 (coming soon) by design. */
export const linkMpesa = async (
  mpesa_phone: string,
  opts?: { label?: string; is_default?: boolean },
): Promise<PaymentMethod> => {
  const r = await API.post("users/payment-methods/", {
    kind: "mpesa", mpesa_phone, ...opts,
  });
  return r.data;
};

export const setDefaultPaymentMethod = async (id: number): Promise<PaymentMethod> => {
  const r = await API.post(`users/payment-methods/${id}/default/`);
  return r.data;
};

export const removePaymentMethod = async (id: number): Promise<void> => {
  await API.delete(`users/payment-methods/${id}/`);
};
