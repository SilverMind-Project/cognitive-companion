/**
 * Presentational extras (icon, caregiver-friendly blurb) for signal kinds.
 *
 * Signal kinds themselves reach the frontend only through the generated
 * vocabulary (`vocabularies.json`, refreshed by `make contracts`); this map
 * is the single place presentational metadata for a kind lives (DL-M06,
 * extended by DL-M07/DL-M08). A kind missing here is not an error -- it
 * falls back to a generic humanized label and icon, so an unregistered or
 * future kind still renders instead of crashing (platform
 * forward-compatibility rule, cts_contracts/signals.py).
 */

const DEFAULT_ICON = "mdi-bell-outline";

const SIGNAL_KIND_PRESENTATIONS = {
  tea_intent_suspected: {
    icon: "mdi-kettle-steam-outline",
    blurb: "May be starting to make tea",
  },
  same_clothes_suspected: {
    icon: "mdi-tshirt-crew-outline",
    blurb: "Appears to be wearing yesterday's clothes",
  },
  agitation_index: {
    rejectLabel: "Not agitation",
  },
  medication_excess: {
    icon: "mdi-pill-multiple",
    blurb: "A dose beyond the medication schedule",
  },
  hygiene_routine_missed: {
    icon: "mdi-shower-head",
    blurb: "Same clothes and no wash-up detected",
  },
};

export function humanizeKind(kind) {
  return (kind || "").replace(/_/g, " ");
}

/**
 * Return `{ icon, label, blurb, rejectLabel }` for a signal kind, falling back to a generic
 * humanized label and default icon for kinds not registered above. `rejectLabel` names the
 * feedback button that says the signal was wrong.
 */
export function getKindPresentation(kind) {
  const known = SIGNAL_KIND_PRESENTATIONS[kind];
  return {
    icon: known?.icon ?? DEFAULT_ICON,
    label: humanizeKind(kind),
    blurb: known?.blurb ?? "",
    rejectLabel: known?.rejectLabel ?? "Inaccurate",
  };
}

export { SIGNAL_KIND_PRESENTATIONS };
