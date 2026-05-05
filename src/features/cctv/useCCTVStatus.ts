import { useState, useEffect } from "react";
import { getStatus } from "../../services/cctvApi";

export const useCCTVStatus = () => {
  const [connection, setConnection] = useState<"online" | "offline">("offline");
  const [system, setSystem] = useState<"running" | "idle">("idle");

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const data = await getStatus();
        setConnection("online");
        setSystem(data.status === "running" ? "running" : "idle");
      } catch (error) {
        setConnection("offline");
        setSystem("idle");
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  return { connection, system };
};
