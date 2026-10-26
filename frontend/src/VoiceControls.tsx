import { useEffect, useRef, useState } from "react";

import type { Locale } from "./learningTypes";

type RecognitionAlternative = { transcript: string };
type RecognitionResult = ArrayLike<RecognitionAlternative> & { isFinal: boolean };
type RecognitionEvent = {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
};
type RecognitionErrorEvent = { error: string };
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type RecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  }
}

type Props = {
  locale: Locale;
  latestTutorText: string;
  onTranscript: (transcript: string) => void;
};

const labels = {
  English: {
    listen: "Speak your question",
    stopListening: "Stop listening",
    read: "Read the latest answer aloud",
    stopReading: "Stop reading",
    unsupported: "Voice input is not supported in this browser.",
    noVoice: "No speech voice for the selected language is available on this device.",
    failed: "Voice interaction could not start. Check microphone permission and try again.",
  },
  Sinhala: {
    listen: "ඔබේ ප්‍රශ්නය කියන්න",
    stopListening: "සවන් දීම නවත්වන්න",
    read: "අලුත්ම පිළිතුර හඬින් කියවන්න",
    stopReading: "කියවීම නවත්වන්න",
    unsupported: "මෙම බ්‍රවුසරය හඬ ආදානයට සහාය නොදක්වයි.",
    noVoice: "මෙම උපකරණයේ තෝරාගත් භාෂාව සඳහා හඬක් නැහැ.",
    failed: "හඬ ක්‍රියාකාරිත්වය ආරම්භ කළ නොහැකියි. මයික්‍රෆෝන අවසරය පරීක්ෂා කර නැවත උත්සාහ කරන්න.",
  },
  Tamil: {
    listen: "உன் கேள்வியைப் பேசு",
    stopListening: "கேட்பதை நிறுத்து",
    read: "சமீபத்திய பதிலைச் சத்தமாக வாசி",
    stopReading: "வாசிப்பதை நிறுத்து",
    unsupported: "இந்த உலாவியில் குரல் உள்ளீடு ஆதரிக்கப்படவில்லை.",
    noVoice: "இந்தச் சாதனத்தில் தேர்ந்தெடுத்த மொழிக்கான குரல் இல்லை.",
    failed: "குரல் செயல்பாட்டைத் தொடங்க முடியவில்லை. மைக்ரோஃபோன் அனுமதியைச் சரிபார்த்து மீண்டும் முயற்சி செய்.",
  },
} satisfies Record<Locale, Record<string, string>>;

const speechLanguage: Record<Locale, { recognition: string; synthesis: string }> = {
  English: { recognition: "en-LK", synthesis: "en" },
  Sinhala: { recognition: "si-LK", synthesis: "si" },
  Tamil: { recognition: "ta-LK", synthesis: "ta" },
};

export function VoiceControls({ locale, latestTutorText, onTranscript }: Props) {
  const copy = labels[locale];
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");

  useEffect(
    () => () => {
      recognitionRef.current?.stop();
      window.speechSynthesis?.cancel();
    },
    [],
  );

  function toggleListening() {
    setError("");
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      setError(copy.unsupported);
      return;
    }
    try {
      const recognition = new Recognition();
      recognition.lang = speechLanguage[locale].recognition;
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onresult = (event) => {
        const heard: string[] = [];
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          if (result?.isFinal && result[0]?.transcript.trim()) {
            heard.push(result[0].transcript.trim());
          }
        }
        if (heard.length) onTranscript(heard.join(" "));
      };
      recognition.onerror = () => setError(copy.failed);
      recognition.onend = () => {
        setListening(false);
        recognitionRef.current = null;
      };
      recognitionRef.current = recognition;
      recognition.start();
      setListening(true);
    } catch {
      recognitionRef.current = null;
      setListening(false);
      setError(copy.failed);
    }
  }

  function toggleSpeaking() {
    setError("");
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    if (!latestTutorText.trim() || !("speechSynthesis" in window)) {
      setError(copy.noVoice);
      return;
    }
    const voice = window.speechSynthesis
      .getVoices()
      .find((candidate) =>
        candidate.lang.toLowerCase().startsWith(speechLanguage[locale].synthesis),
      );
    if (!voice) {
      setError(copy.noVoice);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(latestTutorText);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.9;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => {
      setSpeaking(false);
      setError(copy.noVoice);
    };
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  }

  return (
    <div className="voice-controls" aria-label={locale === "Tamil" ? "குரல் கட்டுப்பாடுகள்" : locale === "Sinhala" ? "හඬ පාලන" : "Voice controls"}>
      <button type="button" className="secondary-button" onClick={toggleListening} aria-pressed={listening}>
        <span aria-hidden="true">{listening ? "⏹" : "🎙"}</span>
        {listening ? copy.stopListening : copy.listen}
      </button>
      <button type="button" className="secondary-button" onClick={toggleSpeaking} disabled={!latestTutorText.trim()} aria-pressed={speaking}>
        <span aria-hidden="true">{speaking ? "⏹" : "🔊"}</span>
        {speaking ? copy.stopReading : copy.read}
      </button>
      {error && <span className="voice-error" role="status">{error}</span>}
    </div>
  );
}
