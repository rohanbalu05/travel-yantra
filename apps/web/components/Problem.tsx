import { ApiError } from "@/lib/http";
import { useI18n } from "@/lib/i18n";

/** What to say for a failed call: the API's own reason, and whether Try again makes sense. */
export function problemOf(e: unknown): { message: string; retryable: boolean } {
  if (e instanceof ApiError) return { message: e.message, retryable: e.retryable };
  return { message: "Something went wrong. Try again.", retryable: true };
}

export function Problem({ message, retryable, onRetry }: { message: string; retryable: boolean; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="problem" role="alert">
      {/* The app's own fixed messages are in the dictionary; the server's reasons show as sent. */}
      <span>{t(message)}</span>
      {retryable && onRetry && <button type="button" className="btn btn-quiet btn-sm" onClick={onRetry}>{t("Try again")}</button>}
    </div>
  );
}
