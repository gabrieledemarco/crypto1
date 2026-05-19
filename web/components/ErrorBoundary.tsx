import { Component, ReactNode } from "react";

interface Props { children: ReactNode; }
interface State { error: Error | null; }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch() {}

  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: 24, fontFamily: "var(--font-mono)",
          color: "var(--coral)", background: "var(--bg)",
        }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>⚠ SCREEN ERROR</div>
          <div style={{ color: "var(--dim)", fontSize: 12 }}>{this.state.error.message}</div>
          <button
            onClick={() => this.setState({ error: null })}
            style={{
              marginTop: 16, padding: "4px 12px", cursor: "pointer",
              background: "var(--bg-l)", border: "1px solid var(--border-l)",
              color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: 11,
            }}
          >
            RETRY
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
