"""Add WhatsApp campaigns and logs tables

Revision ID: whatsapp_v1
Revises: 
Create Date: 2026-03-03 04:56:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'whatsapp_v1'
down_revision = None  # Update this to the latest revision
branch_labels = None
depends_on = None


def upgrade():
    # Create whatsapp_campaigns table
    op.create_table(
        'whatsapp_campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('media_url', sa.String(length=512), nullable=True),
        sa.Column('provider', sa.Enum('TWILIO', 'MESSAGEBIRD', 'VONAGE', 'WHATSAPP_BUSINESS_API', name='whatsappprovider'), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'SCHEDULED', 'SENDING', 'SENT', 'FAILED', 'CANCELLED', name='whatsappstatus'), nullable=True),
        sa.Column('segment_id', sa.Integer(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('total_recipients', sa.Integer(), nullable=True),
        sa.Column('delivered_count', sa.Integer(), nullable=True),
        sa.Column('failed_count', sa.Integer(), nullable=True),
        sa.Column('read_count', sa.Integer(), nullable=True),
        sa.Column('replied_count', sa.Integer(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['segment_id'], ['segments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_whatsapp_campaigns_id'), 'whatsapp_campaigns', ['id'], unique=False)

    # Create whatsapp_logs table
    op.create_table(
        'whatsapp_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('replied_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['whatsapp_campaigns.id'], ),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_whatsapp_logs_id'), 'whatsapp_logs', ['id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_whatsapp_logs_id'), table_name='whatsapp_logs')
    op.drop_table('whatsapp_logs')
    op.drop_index(op.f('ix_whatsapp_campaigns_id'), table_name='whatsapp_campaigns')
    op.drop_table('whatsapp_campaigns')
    op.execute('DROP TYPE whatsappstatus')
    op.execute('DROP TYPE whatsappprovider')
