"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/dashboard", label: "대시보드" },
  { href: "/lesson", label: "강의실" },
  { href: "/practice", label: "문제 풀기" },
  { href: "/review", label: "복습·오답노트" },
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="main-nav" aria-label="주요 메뉴">
      {links.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`nav-link ${active ? "active" : ""}`}
            aria-current={active ? "page" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
