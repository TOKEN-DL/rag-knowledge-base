import { createBrowserRouter } from 'react-router-dom'
import { BasicLayout } from '@/layouts/BasicLayout'
import { HomePage } from '@/pages/HomePage'
import { DocumentsPage } from "@/pages/DocumentsPage.tsx";
import { DocumentDetailPage } from "@/pages/DocumentDetailPage.tsx";
import {ChatPage} from "@/pages/ChatPage.tsx";
import { EvaluationListPage} from "@/pages/EvaluationListPage.tsx";
import { EvaluationDetailPage } from "@/pages/EvaluationDetailPage.tsx";

export const router = createBrowserRouter([
    {
        path: '/',
        element: <BasicLayout />,
        children: [
            { index: true, element: <HomePage /> },
            { path: 'documents', element: <DocumentsPage/>},
            { path: 'documents', element: <DocumentsPage/>},
            { path: 'documents/:id', element: <DocumentDetailPage/>},
            { path: 'chat', element: <ChatPage/>},
            { path: 'evaluation', element: <EvaluationListPage/>},
            { path: 'evaluation/runs/:id', element: <EvaluationDetailPage/>},

        ],
    },
])