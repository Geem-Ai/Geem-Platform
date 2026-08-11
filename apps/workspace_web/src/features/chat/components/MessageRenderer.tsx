import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MessageRendererProps {
  content: string;
  className?: string;
}

export function MessageRenderer({ content, className }: MessageRendererProps) {
  return (
    <div
      className={`prose prose-sm dark:prose-invert max-w-none [&_pre]:overflow-x-auto [&_code]:text-xs ${className ?? ''}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
