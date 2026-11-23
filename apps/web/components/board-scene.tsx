"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";

import type { SceneObject } from "@/lib/types";

type BoardSceneProps = {
  objects: SceneObject[];
  activeObjectId?: string | null;
  onObjectSelect?: (object: SceneObject) => void;
  instantRender?: boolean;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function objectCaption(object: SceneObject | null): string {
  if (!object) return "";
  if (object.label) return object.label;
  if (object.content) return object.content.split("\n")[0];
  if (object.items?.length) return object.items[0];
  if (object.table?.headers?.length) return object.table.headers.join(" · ");
  return object.type;
}

function Graph({ graph }: { graph: NonNullable<SceneObject["graph"]> }) {
  const width = 420;
  const height = 280;
  const padding = 24;
  const toSvgX = (value: number) =>
    padding + ((value - graph.xMin) / (graph.xMax - graph.xMin)) * (width - padding * 2);
  const toSvgY = (value: number) =>
    height -
    padding -
    ((value - graph.yMin) / (graph.yMax - graph.yMin)) * (height - padding * 2);
  const xAxis = toSvgY(0);
  const yAxis = toSvgX(0);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <rect width={width} height={height} fill="transparent" />
      <line
        x1={padding}
        y1={xAxis}
        x2={width - padding}
        y2={xAxis}
        stroke="rgba(247,235,190,0.35)"
        strokeWidth="1.2"
      />
      <line
        x1={yAxis}
        y1={padding}
        x2={yAxis}
        y2={height - padding}
        stroke="rgba(247,235,190,0.35)"
        strokeWidth="1.2"
      />
      {graph.curves.map((curve) => (
        <polyline
          key={curve.color + curve.points.length}
          fill="none"
          stroke={curve.color}
          strokeWidth="3.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={curve.points.map((point) => `${toSvgX(point[0])},${toSvgY(point[1])}`).join(" ")}
        />
      ))}
      {graph.marks.map((mark) => {
        const x = toSvgX(mark.x);
        const y = toSvgY(mark.y);
        return (
          <g key={mark.label}>
            <circle cx={x} cy={y} r="5.5" fill="#ffd78d" />
            <text x={x + 8} y={y - 8} fill="#f7ebbe" fontSize="14">
              {mark.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

type HandwritingTextProps = {
  text: string;
  delayMs?: number;
  cursor?: boolean;
  speedMs?: number;
  instant?: boolean;
};

function HandwritingText({
  text,
  delayMs = 0,
  cursor = true,
  speedMs = 18,
  instant = false,
}: HandwritingTextProps) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (instant) {
      setCount(text.length);
      return;
    }
    setCount(0);
    if (!text) {
      return;
    }

    let tick: number | null = null;
    const start = window.setTimeout(() => {
      setCount(1);
      tick = window.setInterval(() => {
        setCount((current) => {
          if (current >= text.length) {
            if (tick) {
              window.clearInterval(tick);
            }
            return current;
          }
          return current + 1;
        });
      }, speedMs);
    }, delayMs);

    return () => {
      window.clearTimeout(start);
      if (tick) {
        window.clearInterval(tick);
      }
    };
  }, [delayMs, instant, speedMs, text]);

  const visibleText = text.slice(0, count);
  const done = count >= text.length;

  return (
    <span className={`handwriting-text ${done ? "done" : ""}`}>
      {visibleText.split("\n").map((line, index, lines) => (
        <Fragment key={`${line}-${index}`}>
          {line}
          {index < lines.length - 1 ? <br /> : null}
        </Fragment>
      ))}
      {!done && cursor ? <span className="handwriting-cursor" aria-hidden="true" /> : null}
    </span>
  );
}

function Checklist({ object, instantRender }: { object: SceneObject; instantRender: boolean }) {
  return (
    <div className="board-checklist-inner">
      {object.label ? (
        <strong>
          <HandwritingText text={object.label} cursor={false} instant={instantRender} />
        </strong>
      ) : null}
      <ul>
        {(object.items ?? []).map((item, index) => (
          <li key={item}>
            <HandwritingText
              text={item}
              delayMs={index * 180}
              cursor={false}
              instant={instantRender}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

function SceneTable({ object, instantRender }: { object: SceneObject; instantRender: boolean }) {
  if (!object.table) return null;
  return (
    <div className="board-table-wrap">
      <table>
        <thead>
          <tr>
            {object.table.headers.map((header, index) => (
              <th key={header}>
                <HandwritingText
                  text={header}
                  delayMs={index * 120}
                  cursor={false}
                  instant={instantRender}
                />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {object.table.rows.map((row, rowIndex) => (
            <tr key={`${object.id}-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${object.id}-${rowIndex}-${cellIndex}`}>
                  <HandwritingText
                    text={cell}
                    delayMs={rowIndex * 220 + cellIndex * 120}
                    cursor={false}
                    instant={instantRender}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


const MIN_TEXT_WIDTH = 28; // % of board; narrower boxes turn Korean into one-word columns
const LONG_TEXT_CHARS = 22;

function objectText(object: SceneObject): string {
  if (object.content) return object.content;
  if (object.items?.length) return [object.label ?? "", ...object.items].join(" ");
  if (object.table) return [...object.table.headers, ...object.table.rows.flat()].join(" ");
  return object.label ?? "";
}

/** Widen narrow boxes that hold long text, keeping them inside the board. */
function layoutFor(object: SceneObject): CSSProperties {
  let x = object.x;
  let w = object.w;
  const textual = !["graph", "arrow", "badge", "metric", "heading"].includes(object.type);
  if (textual && w !== undefined && w < MIN_TEXT_WIDTH && objectText(object).length > LONG_TEXT_CHARS) {
    w = MIN_TEXT_WIDTH;
    if (x !== undefined && x + w > 96) x = Math.max(2, 96 - w);
  }
  return {
    left: x !== undefined ? `${x}%` : undefined,
    top: object.y !== undefined ? `${object.y}%` : undefined,
    width: w !== undefined ? `${w}%` : undefined,
    height: object.h !== undefined ? `${object.h}%` : undefined,
  };
}

/**
 * Shrinks an object's text (down to 60%) until it fits its box, or the board
 * below it when the box has no fixed height. Re-checks while text is written.
 */
function FitObject({
  object,
  className,
  style,
  children,
  ...rest
}: {
  object: SceneObject;
  className: string;
  style: CSSProperties;
  children: ReactNode;
  onClick?: () => void;
  onKeyDown?: (event: KeyboardEvent<HTMLDivElement>) => void;
  role?: string;
  tabIndex?: number;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const el = ref.current;
    const board = el?.closest(".board") as HTMLElement | null;
    if (!el || !board || typeof ResizeObserver === "undefined") return;
    const check = () => {
      const boardHeight = board.clientHeight;
      const top = ((object.y ?? 0) / 100) * boardHeight;
      const limit = object.h !== undefined ? (object.h / 100) * boardHeight : boardHeight * 0.97 - top;
      const tooTall = el.scrollHeight > limit + 1;
      const tooWide = el.scrollWidth > el.clientWidth + 1;
      // tables scroll inside their own wrapper, so check that box too
      const inner = el.querySelector<HTMLElement>(".board-table-wrap");
      const innerOverflow = inner ? inner.scrollHeight > inner.clientHeight + 1 : false;
      if (tooTall || tooWide || innerOverflow) setScale((current) => (current > 0.6 ? Math.max(0.6, current * 0.92) : current));
    };
    const observer = new ResizeObserver(check);
    observer.observe(el);
    // fixed-height boxes (tables) don't resize while their content is written in
    const content = el.querySelector("table");
    if (content) observer.observe(content);
    check();
    return () => observer.disconnect();
  }, [object.h, object.y, scale]);

  return (
    <div ref={ref} className={className} style={{ ...style, "--fit": scale } as CSSProperties} {...rest}>
      {children}
    </div>
  );
}

export function BoardScene({
  objects,
  activeObjectId,
  onObjectSelect,
  instantRender = false,
}: BoardSceneProps) {
  const activeObject = useMemo(
    () => objects.find((object) => object.id === activeObjectId) ?? null,
    [activeObjectId, objects],
  );

  const focusFrame = useMemo(() => {
    if (
      !activeObject ||
      activeObject.x === undefined ||
      activeObject.y === undefined ||
      activeObject.w === undefined ||
      activeObject.h === undefined
    ) {
      return null;
    }
    const width = activeObject.w;
    const height = activeObject.h;
    const centerX = activeObject.x + width / 2;
    const centerY = activeObject.y + height / 2;
    const dominantSize = Math.max(width, height);
    const scale =
      dominantSize <= 18 ? 1.34 : dominantSize <= 30 ? 1.24 : dominantSize <= 42 ? 1.16 : 1.08;
    const translateX = clamp(50 - centerX * scale, -34, 34);
    const translateY = clamp(45 - centerY * scale, -28, 28);
    const ringPadding = dominantSize <= 22 ? 1.8 : 1.2;
    return {
      canvasStyle: {
        transform: `translate(${translateX}%, ${translateY}%) scale(${scale})`,
      } satisfies CSSProperties,
      ringStyle: {
        left: `${Math.max(0, activeObject.x - ringPadding)}%`,
        top: `${Math.max(0, activeObject.y - ringPadding)}%`,
        width: `${Math.min(96, width + ringPadding * 2)}%`,
        height: `${Math.min(96, height + ringPadding * 2)}%`,
      } satisfies CSSProperties,
    };
  }, [activeObject]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>, object: SceneObject) {
    if (!onObjectSelect) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onObjectSelect(object);
    }
  }

  return (
    <div className={`board ${activeObject ? "focused" : ""}`}>
      <div className="board-glow" aria-hidden="true" />
      {focusFrame ? <div className="board-focus-veil" aria-hidden="true" /> : null}
      <div className="board-canvas" style={focusFrame?.canvasStyle}>
        {objects.map((object) => {
          const style = layoutFor(object);
          const interactive = Boolean(onObjectSelect);
          return (
            <FitObject
              key={object.id}
              object={object}
              className={`board-object board-${object.type} ${
                activeObjectId === object.id ? "active" : ""
              } ${interactive ? "interactive" : ""}`}
              style={style}
              onClick={() => onObjectSelect?.(object)}
              onKeyDown={(event) => handleKeyDown(event, object)}
              role={interactive ? "button" : undefined}
              tabIndex={interactive ? 0 : undefined}
            >
              {object.type === "graph" && object.graph ? (
                <div className="board-graph">
                  <Graph graph={object.graph} />
                </div>
              ) : object.type === "table" && object.table ? (
                <SceneTable object={object} instantRender={instantRender} />
              ) : object.type === "checklist" && object.items ? (
                <Checklist object={object} instantRender={instantRender} />
              ) : object.type === "arrow" ? null : (
                <HandwritingText
                  text={object.content ?? ""}
                  speedMs={object.type === "heading" ? 26 : object.type === "equation" ? 14 : 18}
                  cursor={object.type !== "badge" && object.type !== "metric"}
                  instant={instantRender}
                />
              )}
            </FitObject>
          );
        })}
        {focusFrame ? <div className="board-focus-ring" style={focusFrame.ringStyle} aria-hidden="true" /> : null}
      </div>
      {activeObject ? <div className="board-focus-caption">{objectCaption(activeObject)}</div> : null}
    </div>
  );
}
