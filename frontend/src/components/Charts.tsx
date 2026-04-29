import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

const colors = ["#2563eb", "#16a34a", "#f97316", "#7c3aed", "#0891b2", "#dc2626"];

function EmptyChart({ label }: { label: string }) {
  return <div className="chart-empty">{label}</div>;
}

export function RequestsArea({ data }: { data: Array<Record<string, string | number>> }) {
  if (data.length === 0) {
    return <EmptyChart label="Usage data appears here after API activity." />;
  }
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="day" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip />
        <Area type="monotone" dataKey="requests" stroke="#2563eb" fill="#bfdbfe" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function StateBar({ data }: { data: Array<Record<string, string | number>> }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis type="number" tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey="state" width={110} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar dataKey="villages" fill="#16a34a" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function PlansPie({ data }: { data: Array<Record<string, string | number>> }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie data={data} dataKey="users" nameKey="plan" outerRadius={90} label>
          {data.map((_, index) => (
            <Cell key={index} fill={colors[index % colors.length]} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function ResponseTimeLine({ data }: { data: Array<Record<string, string | number>> }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="day" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip />
        <Line type="monotone" dataKey="avg_ms" stroke="#f97316" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="max_ms" stroke="#dc2626" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function EndpointBar({ data }: { data: Array<Record<string, string | number>> }) {
  if (data.length === 0) {
    return <EmptyChart label="Endpoint mix appears here after requests are logged." />;
  }
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ bottom: 28 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="endpoint" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" interval={0} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar dataKey="requests" fill="#0891b2" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
