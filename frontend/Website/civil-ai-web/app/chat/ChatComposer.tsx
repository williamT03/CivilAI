import type { FormEvent } from "react";

interface ChatComposerProps {
  input: string;
  isLoadingResponse: boolean;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function ChatComposer({
  input,
  isLoadingResponse,
  onInputChange,
  onSubmit,
}: ChatComposerProps) {
  return (
    <form className="composer-form" onSubmit={onSubmit}>
      <div className="field">
        <label className="field-label" htmlFor="chatPrompt">
          Ask for a cited code answer
        </label>
        <textarea
          id="chatPrompt"
          className="field-textarea composer-input"
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="Ask about setbacks, penalties, permitted uses, noise rules, or a specific section."
          disabled={isLoadingResponse}
        />
      </div>
      <div className="composer-actions">
        <button
          type="submit"
          className="button button-primary"
          disabled={!input.trim() || isLoadingResponse}
        >
          {isLoadingResponse ? "Checking..." : "Ask CivilAI"}
        </button>
      </div>
    </form>
  );
}
