import { getStatus, startCCTV, stopCCTV } from "@/services/cctvApi";

export async function handleBot(message: string): Promise<string> {
  const msg = message.toLowerCase();

  if (msg.includes("start")) {
    try {
      await startCCTV();
      return "CCTV started";
    } catch {
      return "Failed to start CCTV";
    }
  }

  if (msg.includes("stop")) {
    try {
      await stopCCTV();
      return "CCTV stopped";
    } catch {
      return "Failed to stop CCTV";
    }
  }

  if (msg.includes("status")) {
    try {
      const data = await getStatus();
      return data.status === "running" ? "System is running" : "System is idle";
    } catch {
      return "Failed to get status";
    }
  }

  if (msg.includes("connection")) {
    try {
      await getStatus();
      return "Backend is online";
    } catch {
      return "Backend is offline";
    }
  }

  return "I didn't understand that command";
}
