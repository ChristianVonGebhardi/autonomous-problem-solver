import clsx from 'clsx'

interface StatCardProps {
  title: string
  value: number | string
  subtitle?: string
  color?: 'red' | 'yellow' | 'blue' | 'green' | 'gray'
  icon?: React.ReactNode
}

const colorMap = {
  red: 'border-red-200 bg-red-50',
  yellow: 'border-yellow-200 bg-yellow-50',
  blue: 'border-blue-200 bg-blue-50',
  green: 'border-green-200 bg-green-50',
  gray: 'border-gray-200 bg-white',
}

const valueColorMap = {
  red: 'text-red-700',
  yellow: 'text-yellow-700',
  blue: 'text-blue-700',
  green: 'text-green-700',
  gray: 'text-gray-900',
}

export default function StatCard({ title, value, subtitle, color = 'gray', icon }: StatCardProps) {
  return (
    <div className={clsx('rounded-xl border p-5', colorMap[color])}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className={clsx('text-3xl font-bold mt-1', valueColorMap[color])}>{value}</p>
          {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
        </div>
        {icon && <div className="text-2xl">{icon}</div>}
      </div>
    </div>
  )
}