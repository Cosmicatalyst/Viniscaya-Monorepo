"use client";
import { createContext, useContext } from "react";
export const ReportChatContext = createContext<(jobId: string) => void>(() => {});
export const useReportChat = () => useContext(ReportChatContext);
