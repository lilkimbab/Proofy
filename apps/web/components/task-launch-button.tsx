"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import type { Task } from "@/lib/types";

type TaskLaunchButtonProps = {
  task: Task;
  className?: string;
};

export function TaskLaunchButton({ task, className = "button ghost" }: TaskLaunchButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    const launch = task.launch;
    if (!launch) {
      if (task.type === "review") {
        router.push("/review");
      }
      return;
    }

    setLoading(true);
    try {
      if (launch.mode === "lesson" || launch.mode === "practice") {
        if (launch.bundleId && launch.lessonId && launch.problemSetId) {
          await api.activateContent({
            bundleId: launch.bundleId,
            lessonId: launch.lessonId,
            problemSetId: launch.problemSetId,
            problemId: launch.problemId,
          });
        }
        router.push(launch.href || (launch.mode === "lesson" ? "/lesson" : "/practice"));
        return;
      }

      router.push(launch.href || "/review");
    } finally {
      setLoading(false);
    }
  }

  const label = task.launch?.ctaLabel ?? (task.type === "lesson" ? "강의 시작" : task.type === "practice" ? "문제 풀기" : "복습 보기");

  return (
    <button className={className} type="button" onClick={handleClick} disabled={loading}>
      {loading ? "여는 중..." : label}
    </button>
  );
}
