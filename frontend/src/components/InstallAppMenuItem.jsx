import { useEffect, useState } from "react";
import { Download, Check } from "lucide-react";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { toast } from "sonner";

/**
 * Install-app dropdown row for the topbar user menu.
 * Chromium fires `beforeinstallprompt` — capture and expose an Install action.
 * On Firefox/Safari (no event) render a disabled item with a hint.
 */
export function InstallAppMenuItem() {
  const [prompt, setPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    const onBip = (e) => { e.preventDefault(); setPrompt(e); };
    const onInstalled = () => { setInstalled(true); setPrompt(null); };
    window.addEventListener("beforeinstallprompt", onBip);
    window.addEventListener("appinstalled", onInstalled);
    // If already running as standalone, treat as installed.
    const standalone = window.matchMedia("(display-mode: standalone)").matches ||
                       window.navigator.standalone === true;
    if (standalone) setInstalled(true);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBip);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const doInstall = async (e) => {
    e.preventDefault();
    if (!prompt) return;
    prompt.prompt();
    const { outcome } = await prompt.userChoice.catch(() => ({ outcome: "dismissed" }));
    if (outcome === "accepted") {
      toast.success("UBOS installed as a desktop app");
    }
    setPrompt(null);
  };

  if (installed) {
    return (
      <DropdownMenuItem disabled data-testid="install-app-installed">
        <Check className="w-4 h-4 mr-2 text-emerald-600" />
        <span>App installed</span>
      </DropdownMenuItem>
    );
  }

  if (prompt) {
    return (
      <DropdownMenuItem onSelect={doInstall} data-testid="install-app-item">
        <Download className="w-4 h-4 mr-2" />
        <span>Install UBOS as an app</span>
      </DropdownMenuItem>
    );
  }

  // Fallback for Firefox/Safari — surface option but disabled with a hint.
  return (
    <DropdownMenuItem
      disabled
      onSelect={(e) => {
        e.preventDefault();
        toast("Install from the browser", {
          description: "Use your browser's address bar or File → Add to Home Screen.",
        });
      }}
      data-testid="install-app-fallback"
    >
      <Download className="w-4 h-4 mr-2" />
      <span>Install app… <span className="text-xs text-muted-foreground ml-1">(browser menu)</span></span>
    </DropdownMenuItem>
  );
}
