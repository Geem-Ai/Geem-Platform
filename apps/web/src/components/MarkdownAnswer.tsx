import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  content: string;
  className?: string;
  placeholder?: string;
};

export default function MarkdownAnswer({ content, className, placeholder = "…" }: Props) {
  const text = content.trim();
  if (!text) {
    return (
      <div className={className ? `markdown-answer ${className}` : "markdown-answer"} dir="auto">
        <p className="muted">{placeholder}</p>
      </div>
    );
  }

  return (
    <div className={className ? `markdown-answer ${className}` : "markdown-answer"} dir="auto">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
