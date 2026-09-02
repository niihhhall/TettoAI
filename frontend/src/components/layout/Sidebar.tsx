import React from 'react'
import { NavLink } from 'react-router-dom'
import { Icon } from '@iconify/react'

interface NavItem {
    label: string
    icon: string
    path: string
}

interface SidebarProps {
    onLogout: () => void
    isOpen: boolean
    setIsOpen: (open: boolean) => void
    isCollapsed: boolean
    onToggleCollapse: () => void
}

const navItems: NavItem[] = [
    { label: 'Live Feed', icon: 'solar:pulse-2-linear', path: '/' },
    { label: 'Claims', icon: 'solar:clipboard-list-linear', path: '/leads' },
    { label: 'Crew Manager', icon: 'solar:users-group-rounded-linear', path: '/instances' },
    { label: 'Jobsites', icon: 'solar:map-point-linear', path: '/jobsites' },
    { label: 'Company Branches', icon: 'solar:buildings-3-linear', path: '/branches' },
]

export const Sidebar: React.FC<SidebarProps> = ({
    onLogout,
    isOpen,
    setIsOpen,
    isCollapsed,
    onToggleCollapse
}) => {
    return (
        <>
            {/* Mobile Overlay */}
            <div
                className={`fixed inset-0 bg-ink/40 backdrop-blur-sm z-40 lg:hidden transition-opacity ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
                    }`}
                onClick={() => setIsOpen(false)}
            ></div>

            <aside className={`fixed lg:static inset-y-0 left-0 z-50 transition-all duration-300 glass-card-sidebar flex flex-col shadow-xl lg:shadow-none
                ${isCollapsed ? 'w-[76px]' : 'w-64'}
                ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
            `}>
                {/* Collapse toggle */}
                <button
                    onClick={onToggleCollapse}
                    className="hidden lg:flex absolute -right-3 top-20 w-6 h-6 bg-white border border-border rounded-full items-center justify-center text-ink-faint hover:text-brand hover:border-brand/40 transition-all duration-200 z-[60] shadow-card"
                    aria-label="Toggle sidebar"
                >
                    <Icon icon={isCollapsed ? 'solar:alt-arrow-right-linear' : 'solar:alt-arrow-left-linear'} width="14" />
                </button>

                {/* Branding */}
                <div className={`flex items-center gap-3 group cursor-pointer pt-7 pb-2 px-5 ${isCollapsed ? 'justify-center px-0' : ''}`}>
                    <div className="w-10 h-10 rounded-xl overflow-hidden shrink-0 group-hover:scale-105 transition-transform">
                        <img src="/logo.jpg" alt="CodeVerity logo" className="w-full h-full object-cover" />
                    </div>
                    {!isCollapsed && (
                        <div className="animate-fade-right overflow-hidden whitespace-nowrap">
                            <h2 className="text-lg font-extrabold text-ink tracking-tight leading-none">Code<span className="text-brand">Verity</span></h2>
                            <p className="text-[10px] text-ink-muted font-medium mt-1 tracking-wide">Field Console</p>
                        </div>
                    )}
                </div>

                <nav className={`flex-1 space-y-1 mt-6 px-3 ${isCollapsed ? '' : ''}`}>
                    {!isCollapsed && (
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-faint px-3 mb-1.5">
                            Workspace
                        </p>
                    )}
                    {navItems.map((item) => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.path === '/'}
                            onClick={() => { if (window.innerWidth < 1024) setIsOpen(false) }}
                            title={item.label}
                            className={({ isActive }) => `
                                w-full flex items-center transition-all duration-200 rounded-xl text-sm font-medium
                                ${isCollapsed ? 'px-3 py-3 justify-center' : 'px-3 py-2.5 gap-3'}
                                ${isActive
                                    ? 'bg-brand text-white shadow-lift'
                                    : 'text-ink-soft hover:bg-brand-muted hover:text-brand'}
                            `}
                        >
                            {({ isActive }) => (
                                <>
                                    <Icon icon={item.icon} width="20" className={`shrink-0 ${isActive ? 'text-white' : 'text-ink-muted group-hover:text-brand'}`} />
                                    {!isCollapsed && <span className="truncate animate-fade-right">{item.label}</span>}
                                </>
                            )}
                        </NavLink>
                    ))}
                </nav>

                {/* Footer / Logout */}
                <div className="mt-auto p-4 border-t border-border">
                    <button
                        onClick={onLogout}
                        className={`group w-full flex items-center gap-3 rounded-xl transition-all duration-200 text-sm font-medium text-ink-muted hover:text-red-600 hover:bg-red-50 ${isCollapsed ? 'justify-center p-3' : 'px-3 py-2.5'}`}
                        title={isCollapsed ? 'Disconnect' : ''}
                    >
                        <Icon icon="solar:logout-2-linear" width="20" className="shrink-0" />
                        {!isCollapsed && <span>Sign out</span>}
                    </button>
                </div>
            </aside>
        </>
    )
}
