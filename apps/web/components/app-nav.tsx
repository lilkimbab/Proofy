"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/dashboard", label: "오늘 학습" },
  { href: "/practice", label: "문제 풀기" },
  { href: "/review", label: "다시 보기" }
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="topnav">
      {links.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={`nav-link ${
            link.href === "/"
              ? pathname === link.href
                ? "active"
                : ""
              : pathname === link.href || pathname.startsWith(`${link.href}/`)
                ? "active"
                : ""
          }`}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
