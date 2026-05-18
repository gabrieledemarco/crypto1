interface Props {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export function Sparkline({
  data,
  width = 80,
  height = 14,
  color = "#6fd17a",
}: Props) {
  if (!data || data.length < 2)
    return <span style={{ display: "inline-block", width, height }} />;
  const mn = Math.min(...data),
    mx = Math.max(...data);
  const range = mx - mn || 1;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - mn) / range) * (height - 2) - 1;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.2" />
    </svg>
  );
}
