// Chart.jsx — reusable Chart.js wrapper. Registers the pieces we use once and
// exposes a single <Chart type=... data=... /> component. Colours adapt to the
// active theme.
import { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Bar, Line, Doughnut } from 'react-chartjs-2';
import { useTheme } from '../context/ThemeContext';
import { THEMES } from '../styles/themes';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
);

const RENDERERS = { bar: Bar, line: Line, doughnut: Doughnut };

export default function Chart({ type = 'bar', data, options = {}, height = 260 }) {
  const { theme } = useTheme();
  const palette = THEMES[theme] || THEMES.light;
  const Renderer = RENDERERS[type] || Bar;

  const mergedOptions = useMemo(() => {
    const isRadial = type === 'doughnut';
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: palette.text },
          display: options.legend !== false,
        },
        tooltip: { enabled: true },
      },
      scales: isRadial
        ? {}
        : {
            x: { ticks: { color: palette.text }, grid: { color: palette.grid } },
            y: { ticks: { color: palette.text }, grid: { color: palette.grid }, beginAtZero: true },
          },
      ...options,
    };
  }, [type, palette.text, palette.grid, options]);

  if (!data) return null;

  return (
    <div style={{ height }}>
      <Renderer data={data} options={mergedOptions} />
    </div>
  );
}
