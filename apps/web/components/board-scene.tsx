"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import type { CSSProperties, KeyboardEvent } from "react";

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
          const style = {
            left: object.x !== undefined ? `${object.x}%` : undefined,
            top: object.y !== undefined ? `${object.y}%` : undefined,
            width: object.w !== undefined ? `${object.w}%` : undefined,
            height: object.h !== undefined ? `${object.h}%` : undefined
          };
          const interactive = Boolean(onObjectSelect);
          return (
            <div
              key={object.id}
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
            </div>
          );
        })}
        {focusFrame ? <div className="board-focus-ring" style={focusFrame.ringStyle} aria-hidden="true" /> : null}
      </div>
      {activeObject ? <div className="board-focus-caption">{objectCaption(activeObject)}</div> : null}
    </div>
  );
}
