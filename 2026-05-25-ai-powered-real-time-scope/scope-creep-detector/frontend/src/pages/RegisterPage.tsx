import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { Shield } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../api'
import { useAuthStore } from '../store'

interface RegisterForm {
  email: string
  password: string
  full_name: string
  company_name?: string
  hourly_rate: number
}

export default function RegisterPage() {
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()
  const [loading, setLoading] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterForm>({ defaultValues: { hourly_rate: 150 } })

  const onSubmit = async (data: RegisterForm) => {
    setLoading(true)
    try {
      const response = await api.post('/auth/register', data)
      setAuth(response.data.access_token, response.data.user)
      toast.success('Account created! Welcome to ScopeGuard.')
      navigate('/dashboard')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail ?? 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-3">
            <Shield className="w-10 h-10 text-primary-500" />
            <span className="text-3xl font-bold text-white">ScopeGuard AI</span>
          </div>
          <p className="text-slate-400">Stop losing money to scope creep</p>
        </div>

        <div className="card">
          <h2 className="text-xl font-semibold text-white mb-6">Create Account</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Full Name</label>
              <input
                {...register('full_name', { required: 'Full name is required' })}
                type="text"
                placeholder="Jane Doe"
                className="input-field"
              />
              {errors.full_name && (
                <p className="text-red-400 text-xs mt-1">{errors.full_name.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Email</label>
              <input
                {...register('email', {
                  required: 'Email is required',
                  pattern: { value: /\S+@\S+\.\S+/, message: 'Invalid email' },
                })}
                type="email"
                placeholder="you@example.com"
                className="input-field"
              />
              {errors.email && (
                <p className="text-red-400 text-xs mt-1">{errors.email.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Password</label>
              <input
                {...register('password', {
                  required: 'Password is required',
                  minLength: { value: 8, message: 'Must be at least 8 characters' },
                })}
                type="password"
                placeholder="Min. 8 characters"
                className="input-field"
              />
              {errors.password && (
                <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Company / Agency Name <span className="text-slate-500">(optional)</span>
              </label>
              <input
                {...register('company_name')}
                type="text"
                placeholder="Acme Creative Studio"
                className="input-field"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Hourly Rate (USD)
              </label>
              <input
                {...register('hourly_rate', {
                  required: 'Hourly rate is required',
                  min: { value: 1, message: 'Must be at least $1' },
                  valueAsNumber: true,
                })}
                type="number"
                placeholder="150"
                className="input-field"
              />
              <p className="text-slate-500 text-xs mt-1">Used to calculate change order amounts</p>
              {errors.hourly_rate && (
                <p className="text-red-400 text-xs mt-1">{errors.hourly_rate.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full py-3 text-base mt-2"
            >
              {loading ? 'Creating account...' : 'Create Account'}
            </button>
          </form>

          <p className="text-center text-slate-400 text-sm mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}