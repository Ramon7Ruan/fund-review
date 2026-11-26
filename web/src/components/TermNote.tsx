import { useEffect, useId, useRef, useState } from "react";

import { reviewTerms, type ReviewTerm } from "../core/reviewTerms";

export function TermNote({
  term,
  children,
  htmlFor,
}: {
  term: ReviewTerm;
  children: string;
  htmlFor?: string;
}) {
  const id = useId();
  const note = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;

    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !note.current?.contains(event.target)) {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  return (
    <span
      ref={note}
      className="inline-block max-w-full align-middle"
      onPointerLeave={(event) => {
        if (event.pointerType !== "touch") setOpen(false);
      }}
    >
      {htmlFor && <label htmlFor={htmlFor}>{children} </label>}
      <button
        type="button"
        aria-label={`查看${children}的解释`}
        aria-expanded={open}
        aria-controls={id}
        aria-describedby={open ? id : undefined}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((previous) => !previous)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
        className="group inline-flex max-w-full cursor-pointer items-center gap-1 rounded-sm text-left align-middle focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-700"
      >
        {!htmlFor && <span>{children}</span>}
        <span
          aria-hidden="true"
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-sky-700 group-hover:bg-sky-100"
        >
          <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full border border-current text-[10px] font-semibold leading-none">
            ?
          </span>
        </span>
      </button>
      <span
        id={id}
        hidden={!open}
        className="mt-1 max-w-[min(14rem,100%)] break-words border-l-2 border-sky-200 pl-2 text-left text-xs font-normal leading-relaxed text-ink-700"
        style={{ display: open ? "block" : undefined }}
      >
        {reviewTerms[term]}
      </span>
    </span>
  );
}
