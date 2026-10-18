"""节点业务编号生成。"""

from sqlalchemy.orm import Session

from app.models.node import NodeCodeSequence


def allocate_node_code(db: Session) -> str:
    """在当前事务中分配一个不会复用的节点编号。"""

    sequence = db.get(NodeCodeSequence, 1)
    if sequence is None:
        sequence = NodeCodeSequence(id=1, next_value=2)
        db.add(sequence)
        # 立即写入序列表，保证同一事务内连续分配时后续调用可以读取到它。
        db.flush()
        return "N-000001"
    value = sequence.next_value
    sequence.next_value += 1
    return f"N-{value:06d}"
