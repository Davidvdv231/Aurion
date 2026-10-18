import React, { Component, type ErrorInfo, type ReactNode } from "react";
import { Pressable, Text, View } from "react-native";

import { makeStyles } from "@/theme/theme";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return <ErrorFallback message={this.state.error?.message ?? "Unknown error"} onReset={this.handleReset} />;
    }
    return this.props.children;
  }
}

function ErrorFallback({ message, onReset }: { message: string; onReset: () => void }) {
  const styles = useStyles();
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Aurion hit an unexpected error</Text>
      <Text style={styles.message}>{message}</Text>
      <Pressable onPress={onReset} accessibilityRole="button" style={({ pressed }) => [styles.button, pressed && styles.pressed]}>
        <Text style={styles.buttonText}>Try again</Text>
      </Pressable>
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  container: {
    flex: 1,
    justifyContent: "center",
    padding: 32,
    gap: theme.space.md,
    backgroundColor: theme.colors.surface,
  },
  title: {
    ...theme.text.lead,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
  },
  message: {
    ...theme.text.small,
    fontFamily: theme.fonts.mono,
    color: theme.colors.ink2,
  },
  button: {
    alignSelf: "flex-start",
    marginTop: theme.space.md,
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 22,
    borderRadius: theme.radius,
    backgroundColor: theme.colors.buttonBg,
  },
  pressed: {
    opacity: 0.85,
  },
  buttonText: {
    ...theme.text.body,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.buttonFg,
  },
}));
