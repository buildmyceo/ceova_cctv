const API_BASE = "http://localhost:8085";

export const getStatus = async () => {
  const res = await fetch(`${API_BASE}/status`);
  if (!res.ok) {
    throw new Error(`Failed to get status: ${res.statusText}`);
  }
  return res.json();
};

export const startCCTV = async (rtspUrl?: string) => {
  const res = await fetch(`${API_BASE}/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      rtsp_url: rtspUrl || "",
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to start CCTV: ${res.statusText}`);
  }
  return res.json();
};

export const stopCCTV = async () => {
  const res = await fetch(`${API_BASE}/stop`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Failed to stop CCTV: ${res.statusText}`);
  }
};
