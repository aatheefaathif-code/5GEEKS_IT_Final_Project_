import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent,
} from "react";

import { getApiBaseUrl } from "./learningTypes";
import type { Locale } from "./learningTypes";

type Activity = {
  textbook_id: string;
  textbook_title: string;
  source_file: string;
  grade: number;
  subject: string;
  medium: Locale;
  reference_page: number;
  exercise_page: number;
};

type Props = {
  locale: Locale;
  grade: number;
  medium: Locale;
  subject: string;
};

type UndoEntry = {
  pixels: number[];
  previousOverlay: Uint8ClampedArray;
};

type DrawPoint = { x: number; y: number };
type DrawStroke = { color: string; points: DrawPoint[]; tool: "draw" | "erase" };
type ColoringAction =
  | { type: "fill"; entry: UndoEntry }
  | { type: "stroke" };

const palettes = [
  "#ef4444",
  "#f97316",
  "#facc15",
  "#22c55e",
  "#06b6d4",
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
  "#8b5e3c",
  "#202020",
];

const copy = {
  English: {
    title: "Colour and Say",
    intro: "Choose a verified textbook picture, a blank page, or a lined page for writing and drawing.",
    choose: "Choose a textbook picture",
    selectPlaceholder: "Choose an activity page",
    reference: "Textbook example",
    exercise: "Your colouring page",
    reveal: "Show the textbook colours",
    hide: "Hide the example and try by yourself",
    fillTool: "Fill",
    drawTool: "Draw",
    eraserTool: "Eraser",
    textbookPage: "Textbook picture",
    blankPage: "Blank page",
    linedPage: "Lined page",
    blankExercise: "Your blank drawing page",
    linedExercise: "Your lined writing page",
    fillHint: "Fill a closed shape, or choose Draw to colour freely with your finger or mouse.",
    drawHint: "Draw directly on the picture with your finger or mouse. Choose a colour first.",
    blankHint: "Draw anything you like on this blank page. Choose a colour, or use the eraser.",
    linedHint: "Write or draw on the ruled lines. Choose a colour, or use the eraser.",
    colour: "Choose a colour",
    undo: "Undo last action",
    reset: "Start again",
    selected: "Selected colour",
    page: "PDF page",
    loading: "Looking for verified textbook colouring pages…",
    none: "No verified Colour and Say pages are listed for this grade, subject and textbook language yet. Choose another book setting or ask your teacher.",
    loadError: "The textbook picture could not be loaded. Please try again.",
    hint: "Tap a white space inside one outlined object. The colour is kept inside its connected outline; a tap outside a shape will not fill the page.",
    painted: "Nice colouring! Choose another colour or keep practising.",
    notRegion: "Tap inside a large, white part of one outlined object.",
    tooLarge: "That area is open or too large to colour safely. Try tapping inside one closed object.",
    undoDone: "The last colour was removed. Choose a different colour and try again.",
    resetDone: "Your colouring page is clear. Try again!",
    source: "Source",
    ariaCanvas: "Textbook outline page. Choose a colour, then click or tap inside an outlined shape.",
    noSelection: "Choose one of the verified textbook activities above to begin.",
  },
  Sinhala: {
    title: "වර්ණ ගන්වා කියන්න",
    intro: "තහවුරු කළ පෙළපොත් රූපයක්, හිස් පිටුවක් හෝ ලිවීමට සහ ඇඳීමට ඉරි සහිත පිටුවක් තෝරන්න.",
    choose: "පෙළපොත් රූපයක් තෝරන්න",
    selectPlaceholder: "ක්‍රියාකාරකම් පිටුවක් තෝරන්න",
    reference: "පෙළපොත් උදාහරණය",
    exercise: "ඔබේ වර්ණ පිටුව",
    reveal: "පෙළපොතේ වර්ණ පෙන්වන්න",
    hide: "උදාහරණය සඟවා ඔබම උත්සාහ කරන්න",
    fillTool: "වර්ණ පුරවන්න",
    drawTool: "අඳින්න",
    eraserTool: "මකනය",
    textbookPage: "පෙළපොත් රූපය",
    blankPage: "හිස් පිටුව",
    linedPage: "ඉරි සහිත පිටුව",
    blankExercise: "ඔබේ හිස් චිත්‍ර පිටුව",
    linedExercise: "ඔබේ ඉරි සහිත ලිවීමේ පිටුව",
    fillHint: "වසා ඇති රූපයකට වර්ණ පුරවන්න, නැතිනම් ඇඟිල්ලෙන් හෝ මූසිකයෙන් වර්ණ ගැන්වීමට අඳින්න තෝරන්න.",
    drawHint: "ඇඟිල්ලෙන් හෝ මූසිකයෙන් රූපය මත කෙළින්ම අඳින්න. මුලින් වර්ණයක් තෝරන්න.",
    blankHint: "මේ හිස් පිටුවේ ඔබ කැමති දෙයක් අඳින්න. වර්ණයක් තෝරන්න හෝ මකනය භාවිතා කරන්න.",
    linedHint: "ඉරි මත ලියන්න හෝ අඳින්න. වර්ණයක් තෝරන්න හෝ මකනය භාවිතා කරන්න.",
    colour: "වර්ණයක් තෝරන්න",
    undo: "අවසාන ක්‍රියාව ඉවත් කරන්න",
    reset: "නැවත අරඹන්න",
    selected: "තෝරාගත් වර්ණය",
    page: "PDF පිටුව",
    loading: "තහවුරු කළ පෙළපොත් වර්ණ පිටු සොයමින්…",
    none: "මෙම ශ්‍රේණිය, විෂය සහ පෙළපොත් භාෂාව සඳහා තහවුරු කළ “වර්ණ ගන්වා කියන්න” පිටු තවම නැහැ. වෙනත් සැකසුමක් තෝරන්න හෝ ගුරුවරයාගෙන් අසන්න.",
    loadError: "පෙළපොත් රූපය පූරණය කළ නොහැකියි. නැවත උත්සාහ කරන්න.",
    hint: "වසා ඇති රූපයක ඇතුළත සුදු කොටසක් තට්ටු කරන්න. වර්ණය එම රූපයේ රේඛාව තුළ පවතී; රූපයෙන් පිටත තට්ටු කළ විට පිටුවම වර්ණ ගැන්වෙන්නේ නැහැ.",
    painted: "ලස්සනයි! තවත් වර්ණයක් තෝරාගෙන පුහුණු වන්න.",
    notRegion: "වසා ඇති රූපයක විශාල සුදු කොටසක් ඇතුළත තට්ටු කරන්න.",
    tooLarge: "මෙම කොටස විවෘත හෝ වර්ණ ගැන්වීමට විශාලයි. වසා ඇති රූපයක ඇතුළත තට්ටු කරන්න.",
    undoDone: "අවසාන වර්ණය ඉවත් කළා. වෙනත් වර්ණයක් තෝරා නැවත උත්සාහ කරන්න.",
    resetDone: "වර්ණ පිටුව පිරිසිදුයි. නැවත උත්සාහ කරන්න!",
    source: "මූලාශ්‍රය",
    ariaCanvas: "පෙළපොත් outline පිටුව. වර්ණයක් තෝරා රූපයක ඇතුළත තට්ටු කරන්න.",
    noSelection: "ආරම්භ කිරීමට ඉහත තහවුරු කළ පෙළපොත් ක්‍රියාකාරකමක් තෝරන්න.",
  },
  Tamil: {
    title: "வண்ணமிட்டு சொல்வோம்",
    intro: "சரிபார்க்கப்பட்ட பாடநூல் படம், வெற்றுப் பக்கம் அல்லது எழுதவும் வரையவும் கோடுகள் உள்ள பக்கத்தைத் தேர்ந்தெடு.",
    choose: "பாடநூல் படத்தைத் தேர்ந்தெடு",
    selectPlaceholder: "செயல்பாட்டுப் பக்கத்தைத் தேர்ந்தெடு",
    reference: "பாடநூல் மாதிரி",
    exercise: "உன் வண்ணப் பக்கம்",
    reveal: "பாடநூல் வண்ணங்களைக் காட்டு",
    hide: "மாதிரியை மறைத்து நீயே முயற்சி செய்",
    fillTool: "நிரப்பு",
    drawTool: "கையால் வரை",
    eraserTool: "அழிப்பான்",
    textbookPage: "பாடநூல் படம்",
    blankPage: "வெற்றுப் பக்கம்",
    linedPage: "கோடுகள் உள்ள பக்கம்",
    blankExercise: "உன் வெற்றுப் படம் வரையும் பக்கம்",
    linedExercise: "உன் கோடுகள் உள்ள எழுதும் பக்கம்",
    fillHint: "மூடிய படத்துக்குள் நிறத்தை நிரப்பு; அல்லது விரல்/சுட்டியால் சுதந்திரமாக வண்ணமிட “கையால் வரை” என்பதைத் தேர்ந்தெடு.",
    drawHint: "விரல் அல்லது சுட்டியால் படத்தின் மேல் நேரடியாக வரை. முதலில் ஒரு நிறத்தைத் தேர்ந்தெடு.",
    blankHint: "இந்த வெற்றுப் பக்கத்தில் உனக்குப் பிடித்ததை வரை. ஒரு நிறத்தைத் தேர்ந்தெடு அல்லது அழிப்பானைப் பயன்படுத்து.",
    linedHint: "கோடுகள் மீது எழுது அல்லது வரை. ஒரு நிறத்தைத் தேர்ந்தெடு அல்லது அழிப்பானைப் பயன்படுத்து.",
    colour: "ஒரு நிறத்தைத் தேர்ந்தெடு",
    undo: "கடைசி செயலை நீக்கு",
    reset: "மீண்டும் தொடங்கு",
    selected: "தேர்ந்தெடுத்த நிறம்",
    page: "PDF பக்கம்",
    loading: "சரிபார்க்கப்பட்ட பாடநூல் வண்ணப் பக்கங்களைத் தேடுகிறது…",
    none: "இந்த வகுப்பு, பாடம், பாடநூல் மொழிக்கு சரிபார்க்கப்பட்ட “வண்ணமிட்டு சொல்வோம்” பக்கங்கள் இன்னும் இல்லை. வேறு அமைப்பைத் தேர்ந்தெடு அல்லது ஆசிரியரிடம் கேள்.",
    loadError: "பாடநூல் படத்தை ஏற்ற முடியவில்லை. மீண்டும் முயற்சி செய்.",
    hint: "மூடிய படத்தின் உள்ளே உள்ள வெள்ளைப் பகுதியில் தொடு. நிறம் அந்தப் படத்தின் கோட்டுக்குள் இருக்கும்; படத்திற்கு வெளியே தொட்டால் பக்கம் முழுவதும் நிறமிடாது.",
    painted: "அருமையான வண்ணம்! இன்னொரு நிறத்தைத் தேர்ந்தெடுத்து தொடர்ந்து முயற்சி செய்.",
    notRegion: "மூடிய படத்தின் உள்ளே உள்ள பெரிய வெள்ளைப் பகுதியில் தொடு.",
    tooLarge: "இந்தப் பகுதி திறந்திருக்கிறது அல்லது பாதுகாப்பாக வண்ணமிடப் பெரிதாக உள்ளது. ஒரு மூடிய படத்தின் உள்ளே தொடு.",
    undoDone: "கடைசி நிறம் நீக்கப்பட்டது. வேறு நிறத்தைத் தேர்ந்தெடுத்து மீண்டும் முயற்சி செய்.",
    resetDone: "வண்ணப் பக்கம் சுத்தம் செய்யப்பட்டது. மீண்டும் முயற்சி செய்!",
    source: "மூலம்",
    ariaCanvas: "பாடநூல் கோட்டுப்படம். நிறத்தைத் தேர்ந்தெடுத்து படத்தின் உள்ளே தொடு.",
    noSelection: "தொடங்க மேலே உள்ள சரிபார்க்கப்பட்ட பாடநூல் செயல்பாட்டைத் தேர்ந்தெடு.",
  },
} satisfies Record<Locale, Record<string, string>>;

function isActivity(value: unknown): value is Activity {
  return (
    typeof value === "object" &&
    value !== null &&
    "textbook_id" in value &&
    typeof value.textbook_id === "string" &&
    "textbook_title" in value &&
    typeof value.textbook_title === "string" &&
    "source_file" in value &&
    typeof value.source_file === "string" &&
    "grade" in value &&
    typeof value.grade === "number" &&
    "subject" in value &&
    typeof value.subject === "string" &&
    "medium" in value &&
    (value.medium === "English" || value.medium === "Sinhala" || value.medium === "Tamil") &&
    "reference_page" in value &&
    typeof value.reference_page === "number" &&
    "exercise_page" in value &&
    typeof value.exercise_page === "number"
  );
}

function canFill(data: Uint8ClampedArray, index: number) {
  return (
    data[index] > 220 &&
    data[index + 1] > 220 &&
    data[index + 2] > 220
  );
}

export function ColoringActivity({ locale, grade, medium, subject }: Props) {
  const labels = copy[locale];
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawCanvasRef = useRef<HTMLCanvasElement>(null);
  const basePixelsRef = useRef<ImageData | null>(null);
  const overlayRef = useRef<ImageData | null>(null);
  const undoRef = useRef<ColoringAction[]>([]);
  const strokesRef = useRef<DrawStroke[]>([]);
  const activeStrokeRef = useRef<DrawStroke | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [color, setColor] = useState(palettes[0]);
  const [drawMode, setDrawMode] = useState(false);
  const [eraserMode, setEraserMode] = useState(false);
  const [blankPage, setBlankPage] = useState(false);
  const [showReference, setShowReference] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [linedPage, setLinedPage] = useState(false);

  const selected = activities.find(
    (activity) => `${activity.textbook_id}:${activity.exercise_page}` === selectedId,
  );
  const imageRoot = selected
    ? `${getApiBaseUrl()}/learning/coloring-pages/${selected.textbook_id}`
    : "";

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    const basePixels = basePixelsRef.current;
    const overlay = overlayRef.current;
    if (!canvas || !context || !basePixels || !overlay) return;
    const composite = context.createImageData(canvas.width, canvas.height);
    for (let offset = 0; offset < basePixels.data.length; offset += 4) {
      const alpha = overlay.data[offset + 3] / 255;
      composite.data[offset] = Math.round(
        overlay.data[offset] * alpha + basePixels.data[offset] * (1 - alpha),
      );
      composite.data[offset + 1] = Math.round(
        overlay.data[offset + 1] * alpha + basePixels.data[offset + 1] * (1 - alpha),
      );
      composite.data[offset + 2] = Math.round(
        overlay.data[offset + 2] * alpha + basePixels.data[offset + 2] * (1 - alpha),
      );
      composite.data[offset + 3] = 255;
    }
    context.putImageData(composite, 0, 0);
  }, []);

  const redrawStrokes = useCallback(() => {
    const canvas = drawCanvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    for (const stroke of strokesRef.current) {
      if (!stroke.points.length) continue;
      context.beginPath();
      context.moveTo(stroke.points[0].x, stroke.points[0].y);
      for (const point of stroke.points.slice(1)) {
        context.lineTo(point.x, point.y);
      }
      context.strokeStyle = stroke.color;
      context.globalCompositeOperation =
        stroke.tool === "erase" ? "destination-out" : "source-over";
      context.lineWidth = Math.max(8, canvas.width * 0.012);
      context.lineCap = "round";
      context.lineJoin = "round";
      context.stroke();
      if (stroke.points.length === 1) {
        context.beginPath();
        context.arc(
          stroke.points[0].x,
          stroke.points[0].y,
          context.lineWidth / 2,
          0,
          Math.PI * 2,
        );
        context.fillStyle = stroke.color;
        context.globalCompositeOperation =
          stroke.tool === "erase" ? "destination-out" : "source-over";
        context.fill();
      }
      context.globalCompositeOperation = "source-over";
    }
  }, []);

  const setupBlankCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d", { willReadFrequently: true });
    const drawCanvas = drawCanvasRef.current;
    if (!canvas || !context || !drawCanvas) return;
    canvas.width = linedPage ? 993 : 1404;
    canvas.height = linedPage ? 1324 : 993;
    drawCanvas.width = canvas.width;
    drawCanvas.height = canvas.height;
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    if (linedPage) {
      const lineSpacing = 28;
      const marginX = canvas.width * 0.125;
      for (let y = 84, lineIndex = 0; y < canvas.height; y += lineSpacing, lineIndex += 1) {
        context.beginPath();
        context.strokeStyle = lineIndex % 4 < 2 ? "#df7777" : "#6ec6e7";
        context.lineWidth = 1.5;
        context.moveTo(0, y);
        context.lineTo(canvas.width, y);
        context.stroke();
      }
      context.beginPath();
      context.strokeStyle = "#d9534f";
      context.lineWidth = 2;
      context.moveTo(marginX, 0);
      context.lineTo(marginX, canvas.height);
      context.stroke();
    }
    basePixelsRef.current = context.getImageData(0, 0, canvas.width, canvas.height);
    overlayRef.current = context.createImageData(canvas.width, canvas.height);
    undoRef.current = [];
    strokesRef.current = [];
    activeStrokeRef.current = null;
    redrawStrokes();
    setFeedback("");
  }, [linedPage, redrawStrokes]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setActivities([]);
    setSelectedId("");
    setError("");
    setFeedback("");
    void fetch(
      `${getApiBaseUrl()}/learning/coloring-pages?grade=${grade}&medium=${medium}&subject=${encodeURIComponent(subject)}`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        const payload: unknown = await response.json().catch(() => null);
        if (!response.ok || !Array.isArray(payload) || !payload.every(isActivity)) {
          const detail =
            typeof payload === "object" &&
            payload !== null &&
            "detail" in payload &&
            typeof payload.detail === "string"
              ? payload.detail
              : labels.loadError;
          throw new Error(detail);
        }
        setActivities(payload);
        if (payload[0]) {
          setSelectedId(`${payload[0].textbook_id}:${payload[0].exercise_page}`);
        }
      })
      .catch((requestError: unknown) => {
        if (
          requestError instanceof DOMException &&
          requestError.name === "AbortError"
        ) {
          return;
        }
        setError(
          requestError instanceof Error ? requestError.message : labels.loadError,
        );
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [grade, medium, subject, labels.loadError]);

  const setupCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d", { willReadFrequently: true });
    const image = document.getElementById("coloring-exercise-source");
    if (
      !canvas ||
      !context ||
      !(image instanceof HTMLImageElement) ||
      !image.complete ||
      !image.naturalWidth
    ) {
      setError(labels.loadError);
      return;
    }
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const drawCanvas = drawCanvasRef.current;
    if (drawCanvas) {
      drawCanvas.width = image.naturalWidth;
      drawCanvas.height = image.naturalHeight;
    }
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0);
    basePixelsRef.current = context.getImageData(0, 0, canvas.width, canvas.height);
    overlayRef.current = context.createImageData(canvas.width, canvas.height);
    undoRef.current = [];
    strokesRef.current = [];
    activeStrokeRef.current = null;
    redrawStrokes();
    setError("");
    setFeedback("");
  }, [labels.loadError, redrawStrokes]);

  useEffect(() => {
    if (blankPage) setupBlankCanvas();
  }, [blankPage, linedPage, setupBlankCanvas]);

  useEffect(() => {
    if (blankPage) return;
    if (!selected) return;
    const image = document.getElementById("coloring-exercise-source");
    if (image instanceof HTMLImageElement && image.complete && image.naturalWidth) {
      setupCanvas();
    }
  }, [blankPage, selectedId, selected, setupCanvas]);

  function pointOnCanvas(
    event: PointerEvent<HTMLCanvasElement>,
  ): DrawPoint | null {
    const canvas = drawCanvasRef.current;
    if (!canvas) return null;
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return null;
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * canvas.width,
      y: ((event.clientY - bounds.top) / bounds.height) * canvas.height,
    };
  }

  function startStroke(event: PointerEvent<HTMLCanvasElement>) {
    if ((!drawMode && !eraserMode) || (event.pointerType === "mouse" && event.button !== 0)) return;
    const canvas = drawCanvasRef.current;
    const context = canvas?.getContext("2d");
    const point = pointOnCanvas(event);
    if (!canvas || !context || !point) return;
    event.preventDefault();
    if (event.isTrusted) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    const stroke: DrawStroke = {
      color,
      points: [point],
      tool: eraserMode ? "erase" : "draw",
    };
    activeStrokeRef.current = stroke;
    context.beginPath();
    context.arc(
      point.x,
      point.y,
      Math.max(4, canvas.width * 0.006),
      0,
      Math.PI * 2,
    );
    context.globalCompositeOperation =
      stroke.tool === "erase" ? "destination-out" : "source-over";
    context.fillStyle = color;
    context.fill();
    context.globalCompositeOperation = "source-over";
  }

  function continueStroke(event: PointerEvent<HTMLCanvasElement>) {
    const stroke = activeStrokeRef.current;
    const canvas = drawCanvasRef.current;
    const context = canvas?.getContext("2d");
    const point = pointOnCanvas(event);
    if ((!drawMode && !eraserMode) || !stroke || !canvas || !context || !point) return;
    event.preventDefault();
    const previous = stroke.points[stroke.points.length - 1];
    if (!previous) return;
    stroke.points.push(point);
    context.beginPath();
    context.moveTo(previous.x, previous.y);
    context.lineTo(point.x, point.y);
    context.globalCompositeOperation =
      stroke.tool === "erase" ? "destination-out" : "source-over";
    context.strokeStyle = stroke.color;
    context.lineWidth = Math.max(8, canvas.width * 0.012);
    context.lineCap = "round";
    context.lineJoin = "round";
    context.stroke();
    context.globalCompositeOperation = "source-over";
  }

  function finishStroke(event: PointerEvent<HTMLCanvasElement>) {
    const stroke = activeStrokeRef.current;
    if (!stroke) return;
    activeStrokeRef.current = null;
    strokesRef.current = [...strokesRef.current, stroke];
    undoRef.current = [...undoRef.current.slice(-19), { type: "stroke" }];
    setFeedback(labels.painted);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function fillAt(event: ReactMouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    const basePixels = basePixelsRef.current;
    const overlay = overlayRef.current;
    if (!canvas || !basePixels || !overlay) return;
    const bounds = canvas.getBoundingClientRect();
    const x = Math.floor(((event.clientX - bounds.left) / bounds.width) * canvas.width);
    const y = Math.floor(((event.clientY - bounds.top) / bounds.height) * canvas.height);
    if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) return;

    const { width, height } = canvas;
    const start = y * width + x;
    const startByte = start * 4;
    if (!canFill(basePixels.data, startByte)) {
      setFeedback(labels.notRegion);
      return;
    }

    const totalPixels = width * height;
    const maximumRegion = Math.floor(totalPixels * 0.12);
    const queue = new Int32Array(maximumRegion + 1);
    const visited = new Uint8Array(totalPixels);
    let readIndex = 0;
    let writeIndex = 1;
    queue[0] = start;
    visited[start] = 1;
    let tooLarge = false;
    while (readIndex < writeIndex) {
      const pixel = queue[readIndex++];
      const px = pixel % width;
      const py = Math.floor(pixel / width);
      const neighbors = [
        px > 0 ? pixel - 1 : -1,
        px < width - 1 ? pixel + 1 : -1,
        py > 0 ? pixel - width : -1,
        py < height - 1 ? pixel + width : -1,
      ];
      for (const neighbor of neighbors) {
        if (neighbor < 0 || visited[neighbor]) continue;
        visited[neighbor] = 1;
        if (!canFill(basePixels.data, neighbor * 4)) continue;
        if (writeIndex >= maximumRegion) {
          tooLarge = true;
          break;
        }
        queue[writeIndex++] = neighbor;
      }
      if (tooLarge) break;
    }
    if (tooLarge) {
      setFeedback(labels.tooLarge);
      return;
    }

    const changedPixels: number[] = [];
    const red = Number.parseInt(color.slice(1, 3), 16);
    const green = Number.parseInt(color.slice(3, 5), 16);
    const blue = Number.parseInt(color.slice(5, 7), 16);
    const previousOverlay = new Uint8ClampedArray(writeIndex * 4);
    for (let index = 0; index < writeIndex; index += 1) {
      const pixel = queue[index];
      const offset = pixel * 4;
      previousOverlay[index * 4] = overlay.data[offset];
      previousOverlay[index * 4 + 1] = overlay.data[offset + 1];
      previousOverlay[index * 4 + 2] = overlay.data[offset + 2];
      previousOverlay[index * 4 + 3] = overlay.data[offset + 3];
      overlay.data[offset] = red;
      overlay.data[offset + 1] = green;
      overlay.data[offset + 2] = blue;
      overlay.data[offset + 3] = 230;
      changedPixels.push(pixel);
    }
    undoRef.current = [
      ...undoRef.current.slice(-19),
      {
        type: "fill",
        entry: { pixels: changedPixels, previousOverlay },
      },
    ];
    redraw();
    setFeedback(labels.painted);
  }

  function undoLastColor() {
    const canvas = canvasRef.current;
    const overlay = overlayRef.current;
    const action = undoRef.current.pop();
    if (!action) return;
    if (action.type === "stroke") {
      strokesRef.current = strokesRef.current.slice(0, -1);
      redrawStrokes();
      setFeedback(labels.undoDone);
      return;
    }
    if (!canvas || !overlay) return;
    const { entry } = action;
    for (let index = 0; index < entry.pixels.length; index += 1) {
      const pixel = entry.pixels[index];
      if (pixel === undefined) continue;
      const offset = pixel * 4;
      overlay.data[offset] = entry.previousOverlay[index * 4] ?? 0;
      overlay.data[offset + 1] = entry.previousOverlay[index * 4 + 1] ?? 0;
      overlay.data[offset + 2] = entry.previousOverlay[index * 4 + 2] ?? 0;
      overlay.data[offset + 3] = entry.previousOverlay[index * 4 + 3] ?? 0;
    }
    redraw();
    setFeedback(labels.undoDone);
  }

  function resetPage() {
    const overlay = overlayRef.current;
    if (!overlay) return;
    overlay.data.fill(0);
    undoRef.current = [];
    strokesRef.current = [];
    activeStrokeRef.current = null;
    redraw();
    redrawStrokes();
    setFeedback(labels.resetDone);
  }

  function changePageMode(mode: "textbook" | "blank" | "lined") {
    const showBlankPage = mode !== "textbook";
    if (blankPage === showBlankPage && linedPage === (mode === "lined")) return;
    setBlankPage(showBlankPage);
    setLinedPage(mode === "lined");
    setDrawMode(showBlankPage);
    setEraserMode(false);
    setShowReference(false);
    setFeedback("");
    setError("");
  }

  return (
    <section className="coloring-activity" aria-labelledby="coloring-title">
      <div className="coloring-heading">
        <span className="coloring-icon" aria-hidden="true">🎨</span>
        <div>
          <p className="eyebrow">{labels.title}</p>
          <h2 id="coloring-title">{labels.title}</h2>
          <p>{labels.intro}</p>
        </div>
      </div>
      <div className="coloring-tools" role="group" aria-label={labels.title}>
        <button
          type="button"
          className={!blankPage ? "primary-button" : "secondary-button"}
          aria-pressed={!blankPage}
          onClick={() => changePageMode("textbook")}
        >
          {labels.textbookPage}
        </button>
        <button
          type="button"
          className={blankPage && !linedPage ? "primary-button" : "secondary-button"}
          aria-pressed={blankPage && !linedPage}
          onClick={() => changePageMode("blank")}
        >
          {labels.blankPage}
        </button>
        <button
          type="button"
          className={linedPage ? "primary-button" : "secondary-button"}
          aria-pressed={linedPage}
          onClick={() => changePageMode("lined")}
        >
          {labels.linedPage}
        </button>
      </div>
      {!blankPage && <div className="coloring-picker">
        <label htmlFor="coloring-activity-select">{labels.choose}</label>
        <select
          id="coloring-activity-select"
          value={selectedId}
          onChange={(event) => {
            setSelectedId(event.target.value);
            basePixelsRef.current = null;
            overlayRef.current = null;
            undoRef.current = [];
            strokesRef.current = [];
            activeStrokeRef.current = null;
            setFeedback("");
            setError("");
          }}
          disabled={loading || !activities.length}
        >
          <option value="">{labels.selectPlaceholder}</option>
          {activities.map((activity) => (
            <option
              key={`${activity.textbook_id}:${activity.exercise_page}`}
              value={`${activity.textbook_id}:${activity.exercise_page}`}
            >
              {activity.textbook_title !== "unknown"
                ? activity.textbook_title
                : activity.source_file.split(/[\\/]/).pop()}{" "}
              · {labels.page} {activity.exercise_page}
            </option>
          ))}
        </select>
      </div>}
      {loading && <p className="loading-message" role="status">{labels.loading}</p>}
      {!blankPage && !loading && !activities.length && (
        <p className="coloring-empty" role="status">{labels.none}</p>
      )}
      {(selected || blankPage) && (
        <>
          <p className="coloring-instructions">
            {linedPage ? labels.linedHint : blankPage ? labels.blankHint : drawMode || eraserMode ? labels.drawHint : labels.fillHint}
          </p>
          <div className="coloring-tools" role="group" aria-label={labels.title}>
            {!blankPage && <button
                type="button"
                className={!drawMode && !eraserMode ? "primary-button" : "secondary-button"}
                aria-pressed={!drawMode && !eraserMode}
                onClick={() => {
                  setDrawMode(false);
                  setEraserMode(false);
                }}
              >
                {labels.fillTool}
              </button>}
            <button
              type="button"
              className={drawMode && !eraserMode ? "primary-button" : "secondary-button"}
              aria-pressed={drawMode && !eraserMode}
              onClick={() => {
                setDrawMode(true);
                setEraserMode(false);
              }}
            >
              ✎ {labels.drawTool}
            </button>
            <button
              type="button"
              className={eraserMode ? "primary-button" : "secondary-button"}
              aria-pressed={eraserMode}
              onClick={() => {
                setDrawMode(false);
                setEraserMode(true);
              }}
            >
              {labels.eraserTool}
            </button>
          </div>
          <div className={showReference && !blankPage ? "coloring-pages coloring-pages--reference" : "coloring-pages"}>
            {showReference && !blankPage && selected && (
              <article className="coloring-page-panel">
                <h3>{labels.reference} · {labels.page} {selected.reference_page}</h3>
                <img
                  crossOrigin="anonymous"
                  src={`${imageRoot}/${selected.exercise_page}.png?kind=reference&v=1`}
                  alt={`${labels.reference}, ${labels.page} ${selected.reference_page}`}
                  onError={() => setError(labels.loadError)}
                />
              </article>
            )}
            <article className="coloring-page-panel">
              <h3>{linedPage ? labels.linedExercise : blankPage ? labels.blankExercise : `${labels.exercise} · ${labels.page} ${selected?.exercise_page}`}</h3>
              {!blankPage && selected && <img
                  id="coloring-exercise-source"
                  crossOrigin="anonymous"
                  src={`${imageRoot}/${selected.exercise_page}.png?kind=exercise&v=1`}
                  alt={labels.ariaCanvas}
                  onLoad={setupCanvas}
                  onError={() => setError(labels.loadError)}
                  hidden
                />}
              <div className="coloring-canvas-stack">
                <canvas
                  ref={canvasRef}
                  className="coloring-canvas"
                  onClick={(event) => {
                    if (!blankPage && !drawMode && !eraserMode) fillAt(event);
                  }}
                  aria-label={linedPage ? labels.linedHint : blankPage ? labels.blankHint : labels.ariaCanvas}
                />
                <canvas
                  ref={drawCanvasRef}
                  className={
                    drawMode || eraserMode
                      ? "coloring-draw-canvas coloring-draw-canvas--active"
                      : "coloring-draw-canvas"
                  }
                  onPointerDown={startStroke}
                  onPointerMove={continueStroke}
                  onPointerUp={finishStroke}
                  onPointerCancel={finishStroke}
                  aria-label={linedPage ? labels.linedHint : blankPage ? labels.blankHint : labels.drawHint}
                />
              </div>
              {selected && !blankPage && <p className="coloring-source">
                {labels.source}: {selected.textbook_title !== "unknown"
                  ? selected.textbook_title
                  : selected.source_file.split(/[\\/]/).pop()}{" "}
                · {labels.page} {selected.exercise_page}
              </p>}
            </article>
          </div>
          <div className="color-palette" role="group" aria-label={labels.colour}>
            <span>{labels.colour}</span>
            {palettes.map((paletteColor) => (
              <button
                type="button"
                key={paletteColor}
                className={color === paletteColor ? "color-swatch color-swatch--selected" : "color-swatch"}
                style={{ backgroundColor: paletteColor }}
                onClick={() => setColor(paletteColor)}
                aria-label={`${labels.colour} ${paletteColor}`}
                aria-pressed={color === paletteColor}
              />
            ))}
            <span className="selected-color-label">{labels.selected}</span>
            <input
              type="color"
              value={color}
              onChange={(event) => setColor(event.target.value)}
              aria-label={labels.colour}
            />
          </div>
          <div className="coloring-actions">
            <button className="secondary-button" onClick={undoLastColor}>{labels.undo}</button>
            <button className="secondary-button" onClick={resetPage}>{labels.reset}</button>
            {selected && !blankPage && <button
              className="primary-button"
              onClick={() => setShowReference((current) => !current)}
            >
              {showReference ? labels.hide : labels.reveal}
            </button>}
          </div>
        </>
      )}
      {!loading && !selected && !blankPage && activities.length > 0 && (
        <p className="coloring-empty">{labels.noSelection}</p>
      )}
      {feedback && <p className="coloring-feedback" role="status">{feedback}</p>}
      {error && <p className="request-error" role="alert">{error}</p>}
    </section>
  );
}
